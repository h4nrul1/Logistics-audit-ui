# pyrefly: ignore [missing-import]
import streamlit as st
import pandas as pd
import base64
# pyrefly: ignore [missing-import]
from google.cloud import bigquery
from google.cloud import storage
from google.cloud import run_v2
import requests
import time

# Configure Streamlit page
st.set_page_config(
    page_title="Master Dashboard - Logistics Audit",
    page_icon="🚢",
    layout="wide"
)

# Initialize BigQuery client
@st.cache_resource
def get_bq_client():
    return bigquery.Client(project="it-ai-briggs-agentspace")

try:
    client = get_bq_client()
except Exception as e:
    st.error(f"Failed to initialize BigQuery client: {e}")
    client = None

# Initialize GCS client
@st.cache_resource
def get_gcs_client():
    return storage.Client(project="it-ai-briggs-agentspace")

try:
    gcs_client = get_gcs_client()
except Exception as e:
    st.error(f"Failed to initialize GCS client: {e}")
    gcs_client = None

# Data Fetching Functions
@st.cache_data(ttl=60)
def fetch_all_shipments():
    if not client:
        return []
    query = """
    SELECT shipment_id, MAX(processed_at) as processed_at FROM (
        SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.PKL_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.VGM_Tbl`
    ) GROUP BY shipment_id
    """
    try:
        df = client.query(query).to_dataframe()
        return df[['shipment_id', 'processed_at']].to_dict('records')
    except Exception as e:
        st.error(f"Error fetching all shipments: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_anomalies():
    if not client:
        return pd.DataFrame()
    
    # UPDATED: Joins against the raw document tables to ensure the anomaly 
    # belongs to the absolute newest document upload.
    query = """
    WITH LatestDocumentSync AS (
        SELECT shipment_id, MAX(processed_at) as true_latest_time 
        FROM (
            SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl`
            UNION ALL
            SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.PKL_Tbl`
            UNION ALL
            SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl`
            UNION ALL
            SELECT shipment_id, processed_at FROM `it-ai-briggs-agentspace.logistics_dataset.VGM_Tbl`
        ) 
        GROUP BY shipment_id
    )
    SELECT 
        a.shipment_id, 
        a.discrepancy_category, 
        a.field_flagged, 
        a.expected_value, 
        a.actual_value,
        a.processed_at
    FROM `it-ai-briggs-agentspace.logistics_dataset.Shipment_Anomalies_Tbl` a
    JOIN LatestDocumentSync d 
      ON a.shipment_id = d.shipment_id 
      AND a.processed_at = d.true_latest_time
    """
    try:
        return client.query(query).to_dataframe()
    except Exception as e:
        st.error(f"Error fetching anomalies: {e}")
        return pd.DataFrame()

def trigger_ingestion_pipeline():
    """
    Programmatically triggers the Google Cloud Run Job responsible 
    for pulling new PDFs from Google Drive.
    """
    client = run_v2.JobsClient()
    job_name = client.job_path(
        project="it-ai-briggs-agentspace",
        location="us-central1",
        job="shipment-ingestion-job"
    )
    request = run_v2.RunJobRequest(name=job_name)
    operation = client.run_job(request=request)
    operation.result()
    return operation

# Main App Layout
st.title("🚢 Logistics Document Auditing - Master Dashboard")

# Header Section
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("Monitor and audit cross-validation checks across your shipping documents.")
with col2:
    if st.button("🔄 Sync New Documents Now", use_container_width=True, type="primary"):
        with st.spinner("Pipeline running... This may take a minute depending on document volume."):
            try:
                trigger_ingestion_pipeline()
            except Exception as e:
                st.error(f"Failed to trigger the pipeline: {e}")
                st.stop()

        # The Cloud Run Job has finished (PDFs are in GCS), but the downstream
        # event-driven processing (Gemini → BigQuery) is still running async.
        # Poll BigQuery every 15 seconds until data appears before refreshing.
        poll_query = """
            SELECT COUNT(*) as cnt FROM (
                SELECT shipment_id FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl`
                UNION ALL
                SELECT shipment_id FROM `it-ai-briggs-agentspace.logistics_dataset.PKL_Tbl`
                UNION ALL
                SELECT shipment_id FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl`
                UNION ALL
                SELECT shipment_id FROM `it-ai-briggs-agentspace.logistics_dataset.VGM_Tbl`
            )
        """
        max_wait_seconds = 600  # Stop polling after 10 minutes
        poll_interval = 15
        elapsed = 0
        bq_poll_client = get_bq_client()

        with st.spinner("Waiting for documents to finish processing... (checking BigQuery every 15 seconds)"):
            while elapsed < max_wait_seconds:
                try:
                    result = bq_poll_client.query(poll_query).to_dataframe()
                    if result.iloc[0]['cnt'] > 0:
                        break  # Data has arrived — safe to refresh!
                except Exception:
                    pass  # Ignore transient BQ errors during polling
                time.sleep(poll_interval)
                elapsed += poll_interval
            else:
                st.warning("⚠️ Processing is taking longer than expected. Please refresh the page manually in a few minutes.")
                st.stop()

        # Data confirmed in BigQuery — clear caches and reload the dashboard
        st.cache_data.clear()
        st.success("✅ Sync complete! Reloading dashboard...")
        time.sleep(2)
        st.rerun()

st.divider()

# Load Data
with st.spinner("Loading shipment data..."):
    all_shipment_data = fetch_all_shipments()
    anomalies_df = fetch_anomalies()

# Prepare Master Queue Data
if not all_shipment_data and anomalies_df.empty:
    st.warning("No shipment data found or BigQuery query failed.")
    st.stop()

# Determine Failed Shipments
failed_shipment_ids = set()
if not anomalies_df.empty:
    failed_shipment_ids = set(anomalies_df['shipment_id'].unique())

# Ensure all shipments from anomalies_df are also in the queue, 
# in case the union query missed some shipments for some reason.
all_shipment_ids_in_data = {row['shipment_id'] for row in all_shipment_data}
if not anomalies_df.empty:
    missing_ids = set(anomalies_df['shipment_id'].unique()) - all_shipment_ids_in_data
    for missing_id in missing_ids:
        all_shipment_data.append({'shipment_id': missing_id, 'processed_at': None})

# Build Queue DataFrame
queue_data = []
for row in all_shipment_data:
    sid = row['shipment_id']
    status = "Failed" if sid in failed_shipment_ids else "Passed"
    queue_data.append({"shipment_id": sid, "Status": status, "processed_at": row.get('processed_at')})

queue_df = pd.DataFrame(queue_data)
if not queue_df.empty and 'processed_at' in queue_df.columns:
    # 1. Ensure the column is treated as a datetime object in UTC
    queue_df['processed_at'] = pd.to_datetime(queue_df['processed_at'], utc=True)
    
    # 2. Convert to Central Time and format it down to the second
    queue_df['processed_at'] = (
        queue_df['processed_at']
        .dt.tz_convert('America/Chicago')
        .dt.strftime('%Y-%m-%d %H:%M:%S')
    )


# Initialize State
if 'current_view' not in st.session_state:
    st.session_state.current_view = 'master'
if 'selected_shipment' not in st.session_state:
    st.session_state.selected_shipment = None
if 'processed_at_sort' not in st.session_state:
    st.session_state.processed_at_sort = None  # None, 'asc', or 'desc'

# Routing Logic
if st.session_state.current_view == 'master':
    st.subheader("Master Audit Queue")
    
    st.markdown("##### Filter & Sort Shipments")
    filter_col1, filter_col2, filter_col3 = st.columns([2, 2, 1.5])
    with filter_col1:
        search_term = st.text_input("Search by Shipment ID", "")
    with filter_col2:
        status_filter = st.multiselect("Filter by Status", ["Passed", "Failed"], default=["Passed", "Failed"])
    with filter_col3:
        sort_state = st.session_state.processed_at_sort
        if sort_state == 'asc':
            sort_btn_label = "Processed At 🔼 (Asc)"
        elif sort_state == 'desc':
            sort_btn_label = "Processed At 🔽 (Desc)"
        else:
            sort_btn_label = "Processed At ↕️ (Default)"
        
        st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
        if st.button(sort_btn_label, key="sort_processed_at_btn", help="Click to toggle sorting by processed_at date/time (Ascending -> Descending -> Default)"):
            if st.session_state.processed_at_sort is None:
                st.session_state.processed_at_sort = 'asc'
            elif st.session_state.processed_at_sort == 'asc':
                st.session_state.processed_at_sort = 'desc'
            else:
                st.session_state.processed_at_sort = None
            st.rerun()

    if not queue_df.empty:
        filtered_df = queue_df[
            (queue_df['shipment_id'].astype(str).str.contains(search_term, case=False, na=False)) &
            (queue_df['Status'].isin(status_filter))
        ]
        
        # Apply processed_at date/time sorting if toggled
        if st.session_state.processed_at_sort == 'asc':
            filtered_df = filtered_df.sort_values(by='processed_at', ascending=True, na_position='last')
        elif st.session_state.processed_at_sort == 'desc':
            filtered_df = filtered_df.sort_values(by='processed_at', ascending=False, na_position='last')
    else:
        filtered_df = pd.DataFrame()

    def color_status(val):
        color = 'red' if val == 'Failed' else 'green'
        return f'color: {color}; font-weight: bold'

    if not filtered_df.empty:
        styled_df = filtered_df.style.map(color_status, subset=['Status'])
        event = st.dataframe(
            styled_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row"
        )
        
        if event.selection.rows:
            selected_row_idx = event.selection.rows[0]
            selected_row = filtered_df.iloc[selected_row_idx]
            st.session_state.selected_shipment = selected_row['shipment_id']
            st.session_state.current_view = 'detail'
            st.rerun()
    else:
        st.info("No shipments to display based on current filters.")

elif st.session_state.current_view == 'detail':
    selected_shipment = st.session_state.selected_shipment
    
    if st.button("⬅ Back to Master Queue"):
        st.session_state.current_view = 'master'
        st.session_state.selected_shipment = None
        st.rerun()
        
    st.divider()
    
    st.subheader("Shipment Inspection View")
    st.markdown(f"### Inspecting Shipment: `{selected_shipment}`")
    
    # Get processed_at from queue_df
    shipment_info = queue_df[queue_df['shipment_id'] == selected_shipment]
    if not shipment_info.empty:
        processed_at = shipment_info.iloc[0]['processed_at']
        if pd.notnull(processed_at):
            st.caption(f"**Processed At:** {processed_at}")
            
    insp_col_left, insp_col_right = st.columns([1, 1])
    
    with insp_col_left:
        st.markdown("#### 📄 Document Viewer")
        if not gcs_client:
            st.error("GCS Client not initialized.")
        else:
            bucket_name = "logistic-audit-pdfs"
            prefix = f"shipment_{selected_shipment}/"
            try:
                bucket = gcs_client.bucket(bucket_name)
                blobs = list(bucket.list_blobs(prefix=prefix))
                pdf_blobs = [b for b in blobs if b.name.lower().endswith('.pdf')]
                
                if not pdf_blobs:
                    st.info(f"No PDFs found for shipment {selected_shipment} in GCS bucket {bucket_name}.")
                else:
                    selected_blob = pdf_blobs[0]
                    if len(pdf_blobs) > 1:
                        blob_names = [b.name.split('/')[-1] for b in pdf_blobs]
                        selected_name = st.selectbox("Select Document", options=blob_names)
                        selected_blob = next(b for b in pdf_blobs if b.name.endswith(selected_name))
                        
                    with st.spinner(f"Loading {selected_blob.name.split('/')[-1]}..."):
                        pdf_bytes = selected_blob.download_as_bytes()
                        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf"></iframe>'
                        st.markdown(pdf_display, unsafe_allow_html=True)
            except Exception as e:
                st.error(f"Error fetching PDFs from GCS: {e}")
        
    with insp_col_right:
        st.markdown("#### ⚠️ Identified Anomalies")
        shipment_anomalies = anomalies_df[anomalies_df['shipment_id'] == selected_shipment]
        
        if not shipment_anomalies.empty:
            st.dataframe(
                shipment_anomalies[['discrepancy_category', 'field_flagged', 'expected_value', 'actual_value']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("🎉 No anomalies found! This shipment passed all checks.")
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
import datetime
from pdf_generator import generate_audited_pdf

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

@st.cache_data(ttl=15)
def fetch_all_overrides():
    if not client:
        return pd.DataFrame()
    query = """
    SELECT shipment_id, document_type, field_name, original_value, audited_value
    FROM `it-ai-briggs-agentspace.logistics_dataset.Audited_Overrides_Tbl`
    """
    try:
        return client.query(query).to_dataframe()
    except Exception as e:
        st.error(f"Error fetching overrides: {e}")
        return pd.DataFrame()

def fetch_document_data(shipment_id, doc_type):
    if not client:
        return {}
    table_map = {
        "CIV": "CIV_Tbl",
        "PKL": "PKL_Tbl",
        "SLI": "SLI_Tbl",
        "VGM": "VGM_Tbl"
    }
    table_name = table_map.get(doc_type)
    if not table_name:
        return {}
    query = f"""
    SELECT * FROM `it-ai-briggs-agentspace.logistics_dataset.{table_name}`
    WHERE shipment_id = @shipment_id
    ORDER BY processed_at DESC
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id)
        ]
    )
    try:
        df = client.query(query, job_config=job_config).to_dataframe()
        if not df.empty:
            return df.iloc[0].to_dict()
    except Exception as e:
        st.error(f"Error fetching original {doc_type} data: {e}")
    return {}

def ensure_list(val):
    if val is None:
        return []
    if hasattr(val, "tolist"):
        try:
            return val.tolist()
        except Exception:
            pass
    if isinstance(val, list):
        return val
    try:
        return list(val)
    except Exception:
        return []

def fetch_resolved_document_data(shipment_id, doc_type):
    # 1. Fetch original raw data
    data = fetch_document_data(shipment_id, doc_type)
    if not data:
        return {}
    
    if "items" in data:
        data["items"] = ensure_list(data["items"])

    # 2. Fetch overrides for this shipment and doc_type
    if not client:
        return data
        
    query = """
    SELECT field_name, audited_value
    FROM `it-ai-briggs-agentspace.logistics_dataset.Audited_Overrides_Tbl`
    WHERE shipment_id = @shipment_id AND document_type = @doc_type
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id),
            bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type)
        ]
    )
    try:
        df = client.query(query, job_config=job_config).to_dataframe()
        for idx, row in df.iterrows():
            field = row['field_name']
            val_str = row['audited_value']
            
            # Cast back to the original field's type if possible
            if field in data:
                orig_val = data[field]
                try:
                    if isinstance(orig_val, float):
                        data[field] = float(val_str)
                    elif isinstance(orig_val, int):
                        data[field] = int(float(val_str))
                    else:
                        data[field] = val_str
                except ValueError:
                    data[field] = val_str
            elif field.startswith("items_"):
                # Parse and apply nested array element overrides (e.g. items_0_gross_weight_kg)
                parts = field.split("_")
                try:
                    array_idx = int(parts[1])
                    sub_field = "_".join(parts[2:])
                    items_list = ensure_list(data.get("items"))
                    if array_idx < len(items_list) and isinstance(items_list[array_idx], dict):
                        orig_val = items_list[array_idx].get(sub_field)
                        try:
                            if isinstance(orig_val, float):
                                items_list[array_idx][sub_field] = float(val_str)
                            elif isinstance(orig_val, int):
                                items_list[array_idx][sub_field] = int(float(val_str))
                            else:
                                items_list[array_idx][sub_field] = val_str
                        except ValueError:
                            items_list[array_idx][sub_field] = val_str
                    data["items"] = items_list
                except Exception:
                    pass
    except Exception as e:
        st.error(f"Error fetching overrides for {doc_type}: {e}")
        
    if doc_type == "SLI" and "items" in data:
        items_list = ensure_list(data["items"])
        if items_list:
            val_sum = sum(float(it.get("value_usd", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
            if val_sum > 0:
                data["total_value_usd"] = val_sum
            gw_sum = sum(float(it.get("gross_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
            if gw_sum > 0:
                data["gross_weight_kg"] = gw_sum
            nw_sum = sum(float(it.get("net_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
            if nw_sum > 0:
                data["net_weight_kg"] = nw_sum

    return data

@st.cache_data(ttl=30)
def fetch_all_shipment_indicators():
    """
    Fetches foreign currencies and $0 item counts for ALL shipments in a single fast BigQuery query.
    Returns: { shipment_id: {"currency": str, "zero_count": int, "hts_groups": dict} }
    """
    client = get_bq_client()
    if not client:
        return {}
        
    query = """
    WITH Currencies AS (
        SELECT shipment_id, UPPER(TRIM(currency)) AS currency FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl` WHERE currency IS NOT NULL
        UNION ALL
        SELECT shipment_id, UPPER(TRIM(currency)) AS currency FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl` WHERE currency IS NOT NULL
    ),
    NormalizedCurrencies AS (
        SELECT shipment_id, ARRAY_AGG(currency ORDER BY currency LIMIT 1)[OFFSET(0)] AS currency
        FROM Currencies
        WHERE currency NOT IN ('USD', '$', '')
        GROUP BY shipment_id
    ),
    CivItems AS (
        SELECT 
            shipment_id,
            COALESCE(item.material_number, 'Unknown Material') AS material,
            COALESCE(item.hts_code, 'Unassigned HTS') AS hts_code,
            COALESCE(item.total_value, item.unit_price) AS val
        FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl`,
        UNNEST(items) AS item
    ),
    SliItems AS (
        SELECT 
            shipment_id,
            'Unknown Material' AS material,
            'Unassigned HTS' AS hts_code,
            item.value_usd AS val
        FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl`,
        UNNEST(items) AS item
    ),
    AllZeroItems AS (
        SELECT shipment_id, material, hts_code FROM CivItems WHERE val = 0.0
        UNION ALL
        SELECT shipment_id, material, hts_code FROM SliItems WHERE val = 0.0 AND shipment_id NOT IN (SELECT shipment_id FROM CivItems WHERE val = 0.0)
    ),
    ZeroBreakdown AS (
        SELECT shipment_id, hts_code, COUNT(*) as zero_count, STRING_AGG(DISTINCT material, ', ') as materials
        FROM AllZeroItems
        GROUP BY shipment_id, hts_code
    )
    SELECT 
        COALESCE(z.shipment_id, c.shipment_id) AS shipment_id,
        c.currency,
        z.hts_code,
        z.zero_count,
        z.materials
    FROM ZeroBreakdown z
    FULL OUTER JOIN NormalizedCurrencies c ON z.shipment_id = c.shipment_id
    """
    try:
        df = client.query(query).to_dataframe()
        indicators_map = {}
        for sid, group in df.groupby("shipment_id"):
            currency = None
            curr_series = group["currency"].dropna()
            if not curr_series.empty:
                currency = curr_series.iloc[0]

            hts_groups = {}
            total_zero = 0
            for _, row in group.iterrows():
                if pd.notna(row["hts_code"]):
                    hts = row["hts_code"]
                    cnt = int(row["zero_count"])
                    total_zero += cnt
                    mats = [m.strip() for m in str(row["materials"]).split(",") if m.strip()]
                    hts_groups[hts] = {"count": cnt, "materials": mats}

            indicators_map[sid] = {
                "currency": currency,
                "zero_count": total_zero,
                "hts_groups": hts_groups
            }
        return indicators_map
    except Exception as e:
        return {}

def get_shipment_indicators(shipment_id):
    all_map = fetch_all_shipment_indicators()
    data = all_map.get(shipment_id, {"currency": None, "zero_count": 0, "hts_groups": {}})
    
    parts = []
    if data["currency"]:
        parts.append(f"💱 {data['currency']}")
    if data["zero_count"] > 0:
        cnt = data["zero_count"]
        parts.append(f"🏷️ {cnt} ($0 item)" if cnt == 1 else f"🏷️ {cnt} ($0 items)")
        
    indicator_str = " | ".join(parts) if parts else "None"
    return indicator_str, data["zero_count"], data["hts_groups"]
def is_value_changed(val1, val2):
    if val1 is None or val2 is None:
        return val1 != val2
    try:
        # Check mathematically with a 0.05 float tolerance to absorb minor extraction rounding/formatting differences
        return abs(float(val1) - float(val2)) > 0.05
    except (ValueError, TypeError):
        return str(val1).strip() != str(val2).strip()

def normalize_field_name(name):
    if not name:
        return ""
    n = name.lower()
    for term in ['_', '(', ')', 'kg', 'lb', 'usd', 'amount', 'value']:
        n = n.replace(term, " ")
    words = [w.strip() for w in n.split() if w.strip()]
    return "".join(words)

def is_anomaly_resolved(flagged_field, shipment_overrides):
    if shipment_overrides.empty:
        return False
        
    norm_flagged = normalize_field_name(flagged_field)
    
    for ov_field in shipment_overrides['field_name'].values:
        norm_ov = normalize_field_name(ov_field)
        if norm_flagged == norm_ov:
            return True
            
        # Special case for SLI nested itemized overrides resolving gross/net weight and financial anomalies
        if norm_flagged == "grossweight" and "gross" in ov_field.lower() and "items_" in ov_field.lower():
            return True
        if norm_flagged == "netweight" and "net" in ov_field.lower() and "items_" in ov_field.lower():
            return True
        if norm_flagged in ["total", "amount", "value", "totalamount", "totalvalue"] and "value" in ov_field.lower() and "items_" in ov_field.lower():
            return True
            
    return False

def is_anomaly_resolved_live(shipment_id, flagged_field):
    """
    Live Python Cross-Validation Engine.
    Evaluates whether a flagged anomaly is truly resolved by re-checking resolved data across documents.
    Returns: '✅ Resolved', '❌ Unresolved', or '⚠️ Typo / Mismatch Introduced'
    """
    overrides_df = fetch_all_overrides()
    shipment_overrides = overrides_df[overrides_df['shipment_id'] == shipment_id] if not overrides_df.empty else pd.DataFrame()
    has_overrides = not shipment_overrides.empty

    norm_flagged = normalize_field_name(flagged_field)

    # 1. Financial Total Mismatch Check
    if norm_flagged in ["totalamount", "totalvalue", "total", "amount", "value"]:
        civ_data = fetch_resolved_document_data(shipment_id, "CIV")
        sli_data = fetch_resolved_document_data(shipment_id, "SLI")
        
        if civ_data and sli_data:
            # Check for foreign currency — bypass financial mismatch check if non-USD
            civ_curr = str(civ_data.get("currency", "USD") or "USD").upper().strip()
            sli_curr = str(sli_data.get("currency", "USD") or "USD").upper().strip()
            if civ_curr not in ["USD", "$"] or sli_curr not in ["USD", "$"]:
                return "✅ Passed (Foreign Currency)"
            civ_val = float(civ_data.get("total_amount", 0.0) or 0.0)
            sli_val = float(sli_data.get("total_value_usd", 0.0) or 0.0)
            sli_items = ensure_list(sli_data.get("items"))
            if sli_items:
                item_sum = sum(float(it.get("value_usd", 0.0) or 0.0) for it in sli_items if isinstance(it, dict))
                if item_sum > 0:
                    sli_val = item_sum
                    
            if abs(civ_val - sli_val) <= 0.05 and civ_val > 0:
                return "✅ Resolved" if has_overrides else "✅ Passed"
            else:
                return "⚠️ Typo / Mismatch Introduced" if has_overrides else "❌ Unresolved"

    # 2. Gross Weight Mismatch Check
    if "gross" in norm_flagged:
        weights = []
        for dt in ["PKL", "SLI", "VGM"]:
            d = fetch_resolved_document_data(shipment_id, dt)
            if d:
                gw = float(d.get("gross_weight_kg", 0.0) or 0.0)
                if dt == "SLI":
                    items_list = ensure_list(d.get("items"))
                    if items_list:
                        item_gw = sum(float(it.get("gross_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
                        if item_gw > 0:
                            gw = item_gw
                if gw > 0:
                    weights.append(gw)
        if len(weights) >= 2:
            if max(weights) - min(weights) <= 0.05 and min(weights) > 0:
                return "✅ Resolved" if has_overrides else "✅ Passed"
            else:
                return "⚠️ Typo / Mismatch Introduced" if has_overrides else "❌ Unresolved"

    # 3. Net Weight Mismatch Check
    if "net" in norm_flagged:
        nets = []
        for dt in ["PKL", "SLI"]:
            d = fetch_resolved_document_data(shipment_id, dt)
            if d:
                nw = float(d.get("net_weight_kg", 0.0) or 0.0)
                if dt == "SLI":
                    items_list = ensure_list(d.get("items"))
                    if items_list:
                        item_nw = sum(float(it.get("net_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
                        if item_nw > 0:
                            nw = item_nw
                if nw > 0:
                    nets.append(nw)
        if len(nets) >= 2:
            if max(nets) - min(nets) <= 0.05 and min(nets) > 0:
                return "✅ Resolved" if has_overrides else "✅ Passed"
            else:
                return "⚠️ Typo / Mismatch Introduced" if has_overrides else "❌ Unresolved"

    # Fallback to override presence if specific rule doesn't apply
    if is_anomaly_resolved(flagged_field, shipment_overrides):
        return "✅ Resolved"
    return "❌ Unresolved"

def is_field_in_doc(field, doc_type):
    if doc_type == "CIV":
        return field in ['total_amount']
    elif doc_type == "PKL":
        return field in ['gross_weight_lb', 'gross_weight_kg', 'net_weight_lb', 'net_weight_kg', 'pallet_count', 'loose_case_count']
    elif doc_type == "SLI":
        return field in ['total_value_usd', 'gross_weight_kg', 'net_weight_kg', 'Gross Weight (KG)', 'Net Weight (KG)', 'Total Amount']
    elif doc_type == "VGM":
        return field in ['gross_weight_lb', 'gross_weight_kg']
    return False

def save_overrides(shipment_id, doc_type, overrides_dict):
    if not client:
        return False
        
    fields = list(overrides_dict.keys())
    if not fields:
        return True
        
    # Clear previous overrides for these fields to avoid duplication
    for field, val in overrides_dict.items():
        delete_query = """
        DELETE FROM `it-ai-briggs-agentspace.logistics_dataset.Audited_Overrides_Tbl`
        WHERE shipment_id = @shipment_id AND document_type = @doc_type AND field_name = @field
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id),
                bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type),
                bigquery.ScalarQueryParameter("field", "STRING", field)
            ]
        )
        try:
            client.query(delete_query, job_config=job_config).result()
        except Exception as e:
            st.error(f"Error clearing previous overrides: {e}")
            return False

    # Insert new override rows via standard transactional DML queries (bypasses streaming buffer)
    orig_data = fetch_document_data(shipment_id, doc_type)
    
    for field, val in overrides_dict.items():
        if field.startswith("items_"):
            parts = field.split("_")
            orig_val_str = ""
            try:
                array_idx = int(parts[1])
                items_list = ensure_list(orig_data.get("items"))
                if array_idx < len(items_list) and isinstance(items_list[array_idx], dict):
                    orig_sub_val = items_list[array_idx].get(sub_field)
                    orig_val_str = str(orig_sub_val) if orig_sub_val is not None and not pd.isna(orig_sub_val) else ""
            except Exception:
                orig_val_str = ""
        else:
            orig_val = orig_data.get(field)
            orig_val_str = str(orig_val) if orig_val is not None and not pd.isna(orig_val) else ""
        
        
        insert_query = """
        INSERT INTO `it-ai-briggs-agentspace.logistics_dataset.Audited_Overrides_Tbl`
        (shipment_id, document_type, field_name, original_value, audited_value, updated_at)
        VALUES
        (@shipment_id, @doc_type, @field, @orig_val, @audited_val, @updated_at)
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id),
                bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type),
                bigquery.ScalarQueryParameter("field", "STRING", field),
                bigquery.ScalarQueryParameter("orig_val", "STRING", orig_val_str),
                bigquery.ScalarQueryParameter("audited_val", "STRING", str(val)),
                bigquery.ScalarQueryParameter("updated_at", "TIMESTAMP", datetime.datetime.now(datetime.timezone.utc))
            ]
        )
        try:
            client.query(insert_query, job_config=job_config).result()
        except Exception as e:
            st.error(f"Error inserting override for {field}: {e}")
            return False
            
    return True


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

# Initialize session state for syncing status
if "is_syncing" not in st.session_state:
    st.session_state.is_syncing = False

def start_sync():
    st.session_state.is_syncing = True

# Header Section
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown("Monitor and audit cross-validation checks across your shipping documents.")
with col2:
    sync_disabled = st.session_state.is_syncing
    button_label = "⏳ Syncing in progress..." if sync_disabled else "🔄 Sync New Documents Now"
    st.button(
        button_label,
        use_container_width=True,
        type="primary",
        disabled=sync_disabled,
        on_click=start_sync,
        key="sync_documents_button"
    )

if st.session_state.is_syncing:
    try:
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
    finally:
        st.session_state.is_syncing = False

    st.rerun()

st.divider()

# Load Data
with st.spinner("Loading shipment data..."):
    all_shipment_data = fetch_all_shipments()
    anomalies_df = fetch_anomalies()
    overrides_df = fetch_all_overrides()

# Prepare Master Queue Data
if not all_shipment_data and anomalies_df.empty:
    st.warning("No shipment data found or BigQuery query failed.")
    st.stop()

# Determine Failed vs Resolved Shipments
failed_shipment_ids = set()
resolved_shipment_ids = set()

if not anomalies_df.empty:
    for sid in anomalies_df['shipment_id'].unique():
        shipment_anoms = anomalies_df[anomalies_df['shipment_id'] == sid]
        if overrides_df.empty:
            failed_shipment_ids.add(sid)
            continue
            
        shipment_overrides = overrides_df[overrides_df['shipment_id'] == sid]
        # Check if all anomalies are covered by overrides (using normalized name matching)
        all_resolved = True
        for anom_field in shipment_anoms['field_flagged'].unique():
            status_res = is_anomaly_resolved_live(sid, anom_field)
            if status_res not in ["✅ Resolved", "✅ Passed"]:
                all_resolved = False
                break
                
        if all_resolved:
            resolved_shipment_ids.add(sid)
        else:
            failed_shipment_ids.add(sid)

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
    if sid in failed_shipment_ids:
        status = "Failed"
    elif sid in resolved_shipment_ids:
        status = "Resolved"
    else:
        status = "Passed"
        
    cats = []
    if not anomalies_df.empty:
        shipment_anoms = anomalies_df[anomalies_df['shipment_id'] == sid]
        if not shipment_anoms.empty and 'discrepancy_category' in shipment_anoms.columns:
            cats = sorted(list(set(shipment_anoms['discrepancy_category'].dropna().unique())))
    categories_str = ", ".join(cats) if cats else "None"

    indicator_str, _, _ = get_shipment_indicators(sid)

    queue_data.append({
        "shipment_id": sid, 
        "Status": status, 
        "Categories": categories_str,
        "Indicators": indicator_str,
        "processed_at": row.get('processed_at')
    })

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
    filter_col1, filter_col2, filter_col3, filter_col4 = st.columns([2, 2, 2, 1.5])
    with filter_col1:
        search_term = st.text_input("Search by Shipment ID", "")
    with filter_col2:
        status_filter = st.multiselect("Filter by Status", ["Passed", "Failed", "Resolved"], default=["Passed", "Failed", "Resolved"])
    with filter_col3:
        category_filter = st.multiselect(
            "Filter by Category", 
            ["Financial", "Weight", "Material Compliance", "None"], 
            default=["Financial", "Weight", "Material Compliance", "None"]
        )
    with filter_col4:
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

    def matches_category(cat_str, selected_categories):
        if not selected_categories:
            return False
        if cat_str == "None":
            return "None" in selected_categories
        row_cats = [c.strip() for c in str(cat_str).split(",")]
        return any(c in selected_categories for c in row_cats)

    if not queue_df.empty:
        filtered_df = queue_df[
            (queue_df['shipment_id'].astype(str).str.contains(search_term, case=False, na=False)) &
            (queue_df['Status'].isin(status_filter)) &
            (queue_df['Categories'].apply(lambda x: matches_category(x, category_filter)))
        ]
        
        # Apply processed_at date/time sorting if toggled
        if st.session_state.processed_at_sort == 'asc':
            filtered_df = filtered_df.sort_values(by='processed_at', ascending=True, na_position='last')
        elif st.session_state.processed_at_sort == 'desc':
            filtered_df = filtered_df.sort_values(by='processed_at', ascending=False, na_position='last')
    else:
        filtered_df = pd.DataFrame()

    def color_status(val):
        if val == 'Failed':
            color = 'red'
        elif val == 'Resolved':
            color = 'orange'
        else:
            color = 'green'
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
            # Clear form widget state to ensure clean defaults for the newly selected shipment
            for key in list(st.session_state.keys()):
                if key.startswith("input_"):
                    del st.session_state[key]
            st.session_state.current_view = 'detail'
            st.rerun()
    else:
        st.info("No shipments to display based on current filters.")

elif st.session_state.current_view == 'detail':
    selected_shipment = st.session_state.selected_shipment
    
    if st.button("⬅ Back to Master Queue"):
        st.session_state.current_view = 'master'
        st.session_state.selected_shipment = None
        for key in list(st.session_state.keys()):
            if key.startswith("input_"):
                del st.session_state[key]
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

    # Check for foreign currency banner
    civ_det_data = fetch_resolved_document_data(selected_shipment, "CIV")
    sli_det_data = fetch_resolved_document_data(selected_shipment, "SLI")
    civ_curr = str(civ_det_data.get("currency", "USD") or "USD").upper().strip() if civ_det_data else "USD"
    sli_curr = str(sli_det_data.get("currency", "USD") or "USD").upper().strip() if sli_det_data else "USD"
    foreign_curr = civ_curr if civ_curr not in ["USD", "$"] else (sli_curr if sli_curr not in ["USD", "$"] else None)
    if foreign_curr:
        st.info(f"💱 **Foreign Currency Detected ({foreign_curr})**: Financial total cross-validation audit is automatically bypassed for this shipment.")

    # Check for $0 items callout & HTS code breakdown table
    _, zero_count, hts_groups = get_shipment_indicators(selected_shipment)
    if zero_count > 0:
        st.warning(f"🏷️ **$0 Priced Items Detected**: Found **{zero_count}** item(s) valued at $0.00 across **{len(hts_groups)}** HTS code(s).")
        
        hts_table_rows = []
        for hts_code, info in sorted(hts_groups.items()):
            mats_str = ", ".join(info["materials"]) if info["materials"] else "N/A"
            hts_table_rows.append({
                "HTS Code": hts_code,
                "$0 Item Count": str(info["count"]),
                "Material / Part Numbers": mats_str
            })
            
        with st.expander("🏷️ View $0 Items Grouped by HTS Code", expanded=True):
            st.dataframe(
                pd.DataFrame(hts_table_rows),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "$0 Item Count": st.column_config.Column(alignment="left")
                }
            )
            
    # 1. Fetch all PDFs and populate document_map upfront
    document_map = {}
    pdf_blobs = []
    bucket_name = "logistic-audit-pdfs"
    if gcs_client:
        prefix = f"shipment_{selected_shipment}/"
        try:
            bucket = gcs_client.bucket(bucket_name)
            blobs = list(bucket.list_blobs(prefix=prefix))
            pdf_blobs = [b for b in blobs if b.name.lower().endswith('.pdf')]
            
            for b in pdf_blobs:
                name = b.name.split('/')[-1]
                if "civ" in name.lower():
                    doc_type = "CIV"
                elif "pkl" in name.lower():
                    doc_type = "PKL"
                elif "sli" in name.lower():
                    doc_type = "SLI"
                elif "vgm" in name.lower():
                    doc_type = "VGM"
                else:
                    doc_type = "OTHER"
                    
                if doc_type not in document_map:
                    document_map[doc_type] = {'original': None, 'audited': None}
                    
                if "_audited" in name.lower():
                    document_map[doc_type]['audited'] = b
                else:
                    document_map[doc_type]['original'] = b
        except Exception as e:
            st.error(f"Error fetching PDFs from GCS: {e}")

    # Now create layout columns
    insp_col_left, insp_col_right = st.columns([1, 1])
    
    with insp_col_left:
        st.markdown("#### 📄 Document Viewer")
        if not gcs_client:
            st.error("GCS Client not initialized.")
        elif not pdf_blobs:
            st.info(f"No PDFs found for shipment {selected_shipment} in GCS bucket {bucket_name}.")
        else:
            # Render Document Type selector
            available_types = sorted(list(document_map.keys()))
            sorted_types = sorted(available_types, key=lambda x: {"CIV": 1, "PKL": 2, "SLI": 3, "VGM": 4}.get(x, 5))
            selected_doc_type = st.selectbox("Select Document Type", options=sorted_types)
            
            doc_versions = document_map[selected_doc_type]
            has_audited = doc_versions['audited'] is not None
            
            if has_audited:
                st.success("✨ Audited version is available for this document!")
                version_choice = st.radio(
                    "Document Version to View",
                    options=["Original PDF", "Audited PDF"],
                    horizontal=True,
                    key=f"version_radio_{selected_doc_type}"
                )
            else:
                version_choice = "Original PDF"
                st.info("Showing original PDF (No corrections audited yet)")
                
            selected_blob = doc_versions['audited'] if version_choice == "Audited PDF" else doc_versions['original']
            
            if selected_blob:
                with st.spinner(f"Loading {selected_blob.name.split('/')[-1]}..."):
                    pdf_bytes = selected_blob.download_as_bytes()
                    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
                    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="600px" type="application/pdf"></iframe>'
                    st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.warning(f"No original PDF file found for {selected_doc_type}.")
        
    with insp_col_right:
        st.markdown("#### ⚠️ Identified Anomalies")
        shipment_anomalies = anomalies_df[anomalies_df['shipment_id'] == selected_shipment].copy()
        
        # Fetch overrides for this shipment
        shipment_overrides = overrides_df[overrides_df['shipment_id'] == selected_shipment] if not overrides_df.empty else pd.DataFrame()
        
        if not shipment_anomalies.empty:
            def get_anomaly_status(row):
                field = row['field_flagged']
                return is_anomaly_resolved_live(selected_shipment, field)
                
            shipment_anomalies['Status'] = shipment_anomalies.apply(get_anomaly_status, axis=1)
            
            st.dataframe(
                shipment_anomalies[['discrepancy_category', 'field_flagged', 'expected_value', 'actual_value', 'Status']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.success("🎉 No anomalies found! This shipment passed all checks.")
            
        st.divider()
        st.markdown("### ✏️ Auditor Corrections & Re-generation")
        st.caption("Expand any document to make manual overrides. Document types with active anomalies are auto-expanded with warnings.")
        
        # Build list of editable document types present for this shipment
        editable_types = [dt for dt in ["CIV", "PKL", "SLI", "VGM"] if dt in document_map]
        
        if not editable_types:
            st.info("No supported logistics documents found for this shipment to edit.")
        else:
            all_new_values = {}
            all_resolved_data = {}
            
            # Helper to preserve typed input values across document selection reruns
            def get_default_input_val(key, default_val):
                if key not in st.session_state:
                    st.session_state[key] = default_val
                return st.session_state[key]

            # Start a single global form for saving all corrections at once
            with st.form(key="global_corrections_form"):
                for dt in editable_types:
                    # 1. Determine if this specific document type has any active anomalies
                    doc_has_anomaly = False
                    if not shipment_anomalies.empty:
                        # An anomaly is for this doc if category contains the doc type, or if the flagged field belongs to this doc
                        is_flagged_field = shipment_anomalies['field_flagged'].apply(lambda f: is_field_in_doc(f, dt))
                        is_matching_cat = shipment_anomalies['discrepancy_category'].str.contains(dt, case=False, na=False)
                        doc_has_anomaly = (is_flagged_field | is_matching_cat).any()
                    
                    # 2. Fetch resolved data for this document type
                    resolved_data = fetch_resolved_document_data(selected_shipment, dt)
                    if not resolved_data:
                        continue
                    all_resolved_data[dt] = resolved_data
                    all_new_values[dt] = {}
                    
                    # 3. Create expander. Expanded by default if there are anomalies!
                    expander_label = f"📝 {dt} Corrections ⚠️" if doc_has_anomaly else f"📝 {dt} Corrections"
                    with st.expander(expander_label, expanded=doc_has_anomaly):
                        if dt == "CIV":
                            val = float(resolved_data.get('total_amount', 0.0))
                            is_flagged = not shipment_anomalies.empty and 'total_amount' in shipment_anomalies['field_flagged'].values
                            label = "Total Invoice Amount (USD) ⚠️" if is_flagged else "Total Invoice Amount (USD)"
                            key_name = f"input_{dt}_total_amount"
                            all_new_values[dt]['total_amount'] = st.number_input(label, value=get_default_input_val(key_name, val), step=100.0, format="%.2f", key=key_name)
                            
                        elif dt == "PKL":
                            for field in ['gross_weight_lb', 'gross_weight_kg', 'net_weight_lb', 'net_weight_kg', 'pallet_count', 'loose_case_count']:
                                val = resolved_data.get(field, 0.0)
                                val = 0.0 if pd.isna(val) else float(val)
                                is_flagged = not shipment_anomalies.empty and field in shipment_anomalies['field_flagged'].values
                                label = f"{field.replace('_', ' ').title()} ⚠️" if is_flagged else field.replace('_', ' ').title()
                                key_name = f"input_{dt}_{field}"
                                
                                if 'count' in field:
                                    all_new_values[dt][field] = st.number_input(label, value=int(get_default_input_val(key_name, val)), step=1, key=key_name)
                                else:
                                    all_new_values[dt][field] = st.number_input(label, value=get_default_input_val(key_name, val), step=10.0, format="%.2f", key=key_name)
                                    
                        elif dt == "SLI":
                            # 1. Total value (USD)
                            val = float(resolved_data.get('total_value_usd', 0.0))
                            is_flagged = not shipment_anomalies.empty and 'Total Amount' in shipment_anomalies['field_flagged'].values
                            label = "Total Value (USD) ⚠️" if is_flagged else "Total Value (USD)"
                            key_name = f"input_{dt}_total_value_usd"
                            all_new_values[dt]['total_value_usd'] = st.number_input(label, value=get_default_input_val(key_name, val), step=100.0, format="%.2f", key=key_name)
                            
                            # 2. Package Line items
                            items_list = ensure_list(resolved_data.get("items"))
                            if items_list:
                                st.write("**Package Line Items weights & values:**")
                                for idx, item in enumerate(items_list):
                                    st.markdown(f"📦 *Item #{idx + 1}*")
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        it_val = float(item.get("value_usd", 0.0))
                                        k1 = f"input_{dt}_items_{idx}_value_usd"
                                        all_new_values[dt][f"items_{idx}_value_usd"] = st.number_input(
                                            "Value (USD)", value=get_default_input_val(k1, it_val), step=10.0, format="%.2f", key=k1
                                        )
                                    with col2:
                                        it_gross = float(item.get("gross_weight_kg", 0.0))
                                        is_gross_flagged = not shipment_anomalies.empty and 'Gross Weight (KG)' in shipment_anomalies['field_flagged'].values
                                        label_gross = "Gross Wt (kg) ⚠️" if is_gross_flagged else "Gross Wt (kg)"
                                        k2 = f"input_{dt}_items_{idx}_gross_weight_kg"
                                        all_new_values[dt][f"items_{idx}_gross_weight_kg"] = st.number_input(
                                            label_gross, value=get_default_input_val(k2, it_gross), step=1.0, format="%.1f", key=k2
                                        )
                                    with col3:
                                        it_net = float(item.get("net_weight_kg", 0.0))
                                        is_net_flagged = not shipment_anomalies.empty and 'Net Weight (KG)' in shipment_anomalies['field_flagged'].values
                                        label_net = "Net Wt (kg) ⚠️" if is_net_flagged else "Net Wt (kg)"
                                        k3 = f"input_{dt}_items_{idx}_net_weight_kg"
                                        all_new_values[dt][f"items_{idx}_net_weight_kg"] = st.number_input(
                                            label_net, value=get_default_input_val(k3, it_net), step=1.0, format="%.1f", key=k3
                                        )
                                
                        elif dt == "VGM":
                            for field in ['gross_weight_lb', 'gross_weight_kg']:
                                val = resolved_data.get(field, 0.0)
                                val = 0.0 if pd.isna(val) else float(val)
                                is_flagged = not shipment_anomalies.empty and field in shipment_anomalies['field_flagged'].values
                                label = f"{field.replace('_', ' ').title()} ⚠️" if is_flagged else field.replace('_', ' ').title()
                                key_name = f"input_{dt}_{field}"
                                all_new_values[dt][field] = st.number_input(label, value=get_default_input_val(key_name, val), step=10.0, format="%.2f", key=key_name)
                
                # Master Save/Regenerate button
                submit_button = st.form_submit_button(
                    "💾 Save All Corrections & Re-generate PDFs",
                    type="primary",
                    use_container_width=True
                )
                
                if submit_button:
                    modified_docs = []
                    with st.spinner("Analyzing overrides and re-generating target PDF documents..."):
                        # Process edits for each document
                        for dt, new_vals in all_new_values.items():
                            orig_vals = all_resolved_data[dt]
                            
                            if dt == "SLI":
                                # Automatically calculate root-level grand weight totals by summing line item inputs
                                calc_gross = sum(float(val) for f, val in new_vals.items() if f.startswith("items_") and f.endswith("_gross_weight_kg"))
                                calc_net = sum(float(val) for f, val in new_vals.items() if f.startswith("items_") and f.endswith("_net_weight_kg"))
                                new_vals['gross_weight_kg'] = calc_gross
                                new_vals['net_weight_kg'] = calc_net
                                
                                # Automatically calculate root-level grand financial value by summing line item values
                                if any(f.startswith("items_") and f.endswith("_value_usd") for f in new_vals.keys()):
                                    calc_val = sum(float(val) for f, val in new_vals.items() if f.startswith("items_") and f.endswith("_value_usd"))
                                    new_vals['total_value_usd'] = calc_val
                            
                            # Check if anything changed
                            has_changes = False
                            changed_values = {}
                            for f, val in new_vals.items():
                                if f.startswith("items_"):
                                    # Nested list element
                                    parts = f.split("_")
                                    try:
                                        array_idx = int(parts[1])
                                        sub_field = "_".join(parts[2:])
                                        items_list = ensure_list(orig_vals.get("items"))
                                        orig_sub_val = None
                                        if array_idx < len(items_list) and isinstance(items_list[array_idx], dict):
                                            orig_sub_val = items_list[array_idx].get(sub_field)
                                            
                                        if is_value_changed(orig_sub_val, val):
                                            has_changes = True
                                            changed_values[f] = val
                                    except Exception:
                                        pass
                                else:
                                    # Standard scalar field
                                    if is_value_changed(orig_vals.get(f), val):
                                        has_changes = True
                                        changed_values[f] = val
                                    
                            if has_changes:
                                t_start = time.time()
                                # Save overrides to BigQuery
                                success = save_overrides(selected_shipment, dt, changed_values)
                                if success:
                                    # Fetch updated fully-resolved data
                                    full_resolved_data = fetch_resolved_document_data(selected_shipment, dt)
                                    original_blob = document_map[dt]['original']
                                    if original_blob:
                                        try:
                                            t0 = time.time()
                                            # Fetch raw original data for text coordinate matching
                                            original_data = fetch_document_data(selected_shipment, dt)
                                            # Download template background
                                            original_pdf_bytes = original_blob.download_as_bytes()
                                            t_dl = time.time() - t0
                                            
                                            t1 = time.time()
                                            # Render and redact direct in-place PDF
                                            pdf_bytes = generate_audited_pdf(
                                                selected_shipment,
                                                dt,
                                                full_resolved_data,
                                                original_data,
                                                original_pdf_bytes
                                            )
                                            t_gen = time.time() - t1
                                            
                                            original_name = original_blob.name
                                            if "_audited" in original_name.lower():
                                                target_name = original_name
                                            else:
                                                target_name = original_name[:-4] + "_audited.pdf"
                                                
                                            t2 = time.time()
                                            bucket = gcs_client.bucket(bucket_name)
                                            blob = bucket.blob(target_name)
                                            blob.upload_from_string(pdf_bytes, content_type="application/pdf")
                                            t_ul = time.time() - t2
                                            
                                            elapsed = time.time() - t_start
                                            print(f"⏱️ [{dt}] PDF Re-generation completed in {elapsed:.2f}s (Download: {t_dl:.2f}s, Vector Render: {t_gen:.2f}s, GCS Upload: {t_ul:.2f}s)")
                                            
                                            modified_docs.append(f"{dt} ({elapsed:.2f}s)")
                                        except Exception as gen_err:
                                            st.error(f"Error during {dt} PDF generation/upload: {gen_err}")
                                    else:
                                        st.error(f"No original GCS blob reference found to name the audited {dt} PDF.")
                                else:
                                    st.error(f"Failed to save corrections for {dt} to BigQuery.")
                                    
                        if modified_docs:
                            st.cache_data.clear()
                            for key in list(st.session_state.keys()):
                                if key.startswith("input_"):
                                    del st.session_state[key]
                            st.success(f"✅ Successfully saved and re-generated PDFs for: {', '.join(modified_docs)}!")
                            time.sleep(1.0)
                            st.rerun()
                        else:
                            st.info("No modifications detected. No documents needed re-generation.")
            
            # Place Reset buttons below the global form
            audited_docs = [dt for dt in editable_types if document_map[dt]['audited'] is not None]
            if audited_docs:
                st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)
                st.markdown("#### 🗑️ Reset Audit Corrections")
                reset_cols = st.columns(len(audited_docs))
                for idx, dt in enumerate(audited_docs):
                    with reset_cols[idx]:
                        reset_btn = st.button(
                            f"Reset {dt}",
                            type="secondary",
                            use_container_width=True,
                            key=f"global_reset_btn_{dt}"
                        )
                        if reset_btn:
                            with st.spinner(f"Resetting {dt} corrections..."):
                                if client:
                                    delete_query = """
                                    DELETE FROM `it-ai-briggs-agentspace.logistics_dataset.Audited_Overrides_Tbl`
                                    WHERE shipment_id = @shipment_id AND document_type = @doc_type
                                    """
                                    job_config = bigquery.QueryJobConfig(
                                        query_parameters=[
                                            bigquery.ScalarQueryParameter("shipment_id", "STRING", selected_shipment),
                                            bigquery.ScalarQueryParameter("doc_type", "STRING", dt)
                                        ]
                                    )
                                    try:
                                        client.query(delete_query, job_config=job_config).result()
                                        
                                        # Delete audited PDF from GCS
                                        audited_blob = document_map[dt]['audited']
                                        if audited_blob:
                                            try:
                                                audited_blob.delete()
                                            except Exception:
                                                pass
                                                
                                        # Clear cache, widget session state, and reload
                                        st.cache_data.clear()
                                        for key in list(st.session_state.keys()):
                                            if key.startswith(f"input_{dt}_"):
                                                del st.session_state[key]
                                                
                                        st.success(f"✅ Successfully reset {dt} corrections!")
                                        time.sleep(1.0)
                                        st.rerun()
                                    except Exception as reset_err:
                                        st.error(f"Error resetting {dt} corrections: {reset_err}")
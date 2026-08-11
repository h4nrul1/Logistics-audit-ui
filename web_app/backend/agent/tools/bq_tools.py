import os
import sys
import json
import datetime
import pandas as pd
from google.cloud import bigquery, storage

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from agent.config import PROJECT_ID, DATASET_ID, BUCKET_NAME

bq_client = bigquery.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)

try:
    import pdf_generator
except ImportError:
    pdf_generator = None

def fetch_master_queue(status_filter: str = "", category_filter: str = "") -> str:
    """Fetch the master audit queue showing all shipments, status (Passed, Failed, Resolved),
    and discrepancy categories (e.g., Weight, Financial, Currency, Material Compliance).
    
    Args:
        status_filter: Optional filter by status ("Failed", "Passed", "Resolved", or empty string for all).
        category_filter: Optional filter by discrepancy type/category (e.g., "Weight", "Financial", "Currency", "Material Compliance", or empty string for all).
    """
    query = f"""
    SELECT shipment_id, CAST(MAX(processed_at) AS STRING) as processed_at
    FROM (
        SELECT shipment_id, processed_at FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `{PROJECT_ID}.{DATASET_ID}.PKL_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl`
        UNION ALL
        SELECT shipment_id, processed_at FROM `{PROJECT_ID}.{DATASET_ID}.VGM_Tbl`
    )
    GROUP BY shipment_id
    ORDER BY processed_at DESC
    """
    try:
        df = bq_client.query(query).to_dataframe()
        
        # Get anomalies
        anom_query = f"SELECT shipment_id, discrepancy_category FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl`"
        anom_df = bq_client.query(anom_query).to_dataframe()
        failed_ids = set(anom_df['shipment_id'].unique()) if not anom_df.empty else set()
        
        # Get overrides
        over_query = f"SELECT DISTINCT shipment_id FROM `{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl`"
        over_df = bq_client.query(over_query).to_dataframe()
        resolved_ids = set(over_df['shipment_id'].unique()) if not over_df.empty else set()

        results = []
        for _, row in df.iterrows():
            sid = str(row['shipment_id'])
            if sid in failed_ids:
                status = "Failed"
            elif sid in resolved_ids:
                status = "Resolved"
            else:
                status = "Passed"

            if status_filter and status.lower() != status_filter.lower():
                continue

            cats = []
            if not anom_df.empty:
                s_anom = anom_df[anom_df['shipment_id'] == sid]
                if not s_anom.empty:
                    cats = list(s_anom['discrepancy_category'].dropna().unique())

            if category_filter:
                match = any(category_filter.lower() in c.lower() for c in cats)
                if not match:
                    continue

            results.append({
                "shipment_id": sid,
                "status": status,
                "discrepancies": ", ".join(cats) if cats else "None",
                "processed_at": row.get('processed_at')
            })

        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error fetching master queue: {e}"

def fetch_shipment_anomalies(shipment_id: str) -> str:
    """Fetch detailed audit anomalies, raw extracted document data, and override status for a specific shipment.
    
    Args:
        shipment_id: The 8-digit shipment ID (e.g., '10351463').
    """
    try:
        # Anomalies
        anom_query = f"""
        SELECT discrepancy_category, field_flagged, expected_value, actual_value, processed_at 
        FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl`
        WHERE shipment_id = '{shipment_id}'
        """
        anom_df = bq_client.query(anom_query).to_dataframe()
        anomalies = anom_df.to_dict(orient="records") if not anom_df.empty else []

        # Fetch doc data summary
        doc_summary = {}
        for dt in ["CIV", "PKL", "SLI", "VGM"]:
            q = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{dt}_Tbl` WHERE shipment_id = '{shipment_id}' ORDER BY processed_at DESC LIMIT 1"
            df = bq_client.query(q).to_dataframe()
            if not df.empty:
                row = df.iloc[0].to_dict()
                # Clean timestamps
                for k, v in list(row.items()):
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        row[k] = v.isoformat()
                doc_summary[dt] = row

        payload = {
            "shipment_id": shipment_id,
            "anomalies": anomalies,
            "documents_found": list(doc_summary.keys()),
            "document_details": doc_summary
        }
        return json.dumps(payload, indent=2, default=str)
    except Exception as e:
        return f"Error fetching shipment anomalies for {shipment_id}: {e}"

def save_field_override(shipment_id: str, doc_type: str, field_name: str, audited_value: str) -> str:
    """Save an auditor correction/override into BigQuery Audited_Overrides_Tbl and re-generate the audited PDF certificate.
    
    Args:
        shipment_id: Shipment ID (e.g. '10351463').
        doc_type: Document type ('CIV', 'PKL', 'SLI', or 'VGM').
        field_name: The field being corrected (e.g. 'gross_weight_kg', 'total_amount').
        audited_value: The new corrected value string (e.g. '1250.0').
    """
    try:
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Fetch original value
        orig_val = ""
        q_orig = f"SELECT {field_name} FROM `{PROJECT_ID}.{DATASET_ID}.{doc_type}_Tbl` WHERE shipment_id = '{shipment_id}' ORDER BY processed_at DESC LIMIT 1"
        try:
            df_o = bq_client.query(q_orig).to_dataframe()
            if not df_o.empty:
                orig_val = str(df_o.iloc[0][field_name])
        except Exception:
            pass

        insert_rows = [{
            "shipment_id": shipment_id,
            "document_type": doc_type.upper(),
            "field_name": field_name,
            "original_value": orig_val,
            "audited_value": str(audited_value),
            "updated_at": now_ts
        }]

        table_id = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
        load_job = bq_client.load_table_from_json(insert_rows, table_id)
        load_job.result()

        # Trigger PDF generation if available
        pdf_status = "No PDF generator available"
        if pdf_generator and hasattr(pdf_generator, 'generate_audited_pdf'):
            try:
                prefix = f"shipment_{shipment_id}/"
                bucket = storage_client.bucket(BUCKET_NAME)
                blobs = list(bucket.list_blobs(prefix=prefix))
                target_blob = None
                for b in blobs:
                    if b.name.lower().endswith('.pdf') and doc_type.lower() in b.name.lower() and "_audited" not in b.name.lower():
                        target_blob = b
                        break

                if target_blob:
                    original_pdf_bytes = target_blob.download_as_bytes()
                    # Generate updated PDF
                    audited_data = {field_name: audited_value}
                    orig_data = {field_name: orig_val}
                    new_pdf_bytes = pdf_generator.generate_audited_pdf(
                        shipment_id,
                        doc_type,
                        audited_data,
                        orig_data,
                        original_pdf_bytes
                    )
                    if new_pdf_bytes:
                        orig_name = target_blob.name
                        audited_name = orig_name if "_audited" in orig_name.lower() else (orig_name[:-4] + "_audited.pdf")
                        out_blob = bucket.blob(audited_name)
                        out_blob.upload_from_string(new_pdf_bytes, content_type="application/pdf")
                        pdf_status = f"Audited PDF generated and uploaded to GCS as {audited_name}"
            except Exception as pdf_err:
                pdf_status = f"PDF generation notice: {pdf_err}"

        return json.dumps({
            "status": "success",
            "message": f"Successfully updated {field_name} on {doc_type} for shipment {shipment_id} to '{audited_value}'.",
            "pdf_status": pdf_status
        }, indent=2)
    except Exception as e:
        return f"Error saving field override: {e}"

def reset_field_overrides(shipment_id: str, doc_type: str) -> str:
    """Reset and delete all corrections for a specific document type on a shipment, restoring original values.
    
    Args:
        shipment_id: Shipment ID (e.g. '10351463').
        doc_type: Document type ('CIV', 'PKL', 'SLI', or 'VGM').
    """
    try:
        table_id = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
        delete_query = f"DELETE FROM `{table_id}` WHERE shipment_id = '{shipment_id}' AND document_type = '{doc_type.upper()}'"
        bq_client.query(delete_query).result()

        # Delete audited PDF blob
        prefix = f"shipment_{shipment_id}/"
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))
        deleted_blobs = []
        for b in blobs:
            if b.name.lower().endswith('.pdf') and doc_type.lower() in b.name.lower() and "_audited" in b.name.lower():
                b.delete()
                deleted_blobs.append(b.name)

        return json.dumps({
            "status": "success",
            "message": f"Successfully reset all overrides for {doc_type} on shipment {shipment_id}.",
            "deleted_audited_pdfs": deleted_blobs
        }, indent=2)
    except Exception as e:
        return f"Error resetting overrides: {e}"

def auto_resolve_shipment_discrepancies(shipment_id: str) -> str:
    """Autonomously inspect all audit anomaly flags for a shipment in BigQuery, determine target document types,
    field names, and target values, execute necessary overrides, and re-generate audited PDF certificates.
    Use this tool whenever a user asks to 'fix', 'correct', 'resolve', or 'apply override' for a shipment!
    
    Args:
        shipment_id: Shipment ID (e.g. '10386317').
    """
    try:
        # Fetch anomalies
        anom_str = fetch_shipment_anomalies(shipment_id)
        data = json.loads(anom_str)
        anomalies = data.get("anomalies", [])
        
        if not anomalies:
            return json.dumps({
                "status": "info",
                "message": f"Shipment {shipment_id} has no recorded anomalies in BigQuery to resolve."
            })

        resolutions = []
        for a in anomalies:
            cat = a.get("discrepancy_category", "")
            field = a.get("field_flagged", "")
            exp_val = a.get("expected_value")
            act_val = a.get("actual_value")

            target_doc = "SLI"
            target_field = "total_value_usd"
            target_val = str(exp_val) if exp_val is not None else str(act_val)

            if "weight" in cat.lower() or "weight" in field.lower():
                target_doc = "PKL"
                target_field = "gross_weight_kg" if "kg" in field.lower() else "gross_weight_lb"
            elif "financial" in cat.lower() or "amount" in field.lower() or "value" in field.lower():
                target_doc = "SLI"
                target_field = "total_value_usd"
            elif "material" in cat.lower() or "compliance" in cat.lower():
                target_doc = "PKL"
                target_field = "material_numbers"

            res = save_field_override(
                shipment_id=shipment_id,
                doc_type=target_doc,
                field_name=target_field,
                audited_value=target_val
            )
            resolutions.append({
                "category": cat,
                "document": target_doc,
                "field": target_field,
                "value_applied": target_val,
                "result": res
            })

        return json.dumps({
            "status": "success",
            "shipment_id": shipment_id,
            "message": f"Autonomously resolved {len(resolutions)} discrepancy flag(s) for shipment {shipment_id}.",
            "resolutions": resolutions
        }, indent=2)
    except Exception as e:
        return f"Error in auto_resolve_shipment_discrepancies: {e}"


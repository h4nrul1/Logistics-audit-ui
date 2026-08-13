import os
import sys
import json
import datetime
import pandas as pd
from google.cloud import bigquery, storage

# Add backend directory and project root to sys.path
tools_dir = os.path.dirname(os.path.abspath(__file__))
agent_dir = os.path.dirname(tools_dir)
backend_dir = os.path.dirname(agent_dir)
webapp_dir = os.path.dirname(backend_dir)
project_root = os.path.dirname(webapp_dir)

for p in [backend_dir, webapp_dir, project_root]:
    if p not in sys.path:
        sys.path.insert(0, p)

from agent.config import PROJECT_ID, DATASET_ID, BUCKET_NAME

bq_client = bigquery.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)

try:
    import pdf_generator
except ImportError:
    pdf_generator = None

def ensure_list(val):
    if val is None:
        return []
    if hasattr(val, "tolist"):
        try:
            return val.tolist()
        except Exception:
            pass
    if isinstance(val, (list, tuple)):
        return [ensure_list(i) if (hasattr(i, "tolist") or isinstance(i, (list, tuple))) else i for i in val]
    try:
        return list(val)
    except Exception:
        return []

def fetch_document_raw(shipment_id: str, doc_type: str) -> dict:
    query = f"""
    SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.{doc_type}_Tbl`
    WHERE shipment_id = @shipment_id
    ORDER BY processed_at DESC
    LIMIT 1
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id)]
    )
    try:
        df = bq_client.query(query, job_config=job_config).to_dataframe()
        if not df.empty:
            row = df.iloc[0].to_dict()
            cleaned = {}
            for k, v in row.items():
                if isinstance(v, (datetime.datetime, datetime.date)):
                    cleaned[k] = v.isoformat()
                elif hasattr(v, "tolist") or isinstance(v, (list, tuple)):
                    cleaned[k] = ensure_list(v)
                elif v is None:
                    cleaned[k] = None
                else:
                    try:
                        if pd.isna(v):
                            cleaned[k] = None
                        else:
                            cleaned[k] = v
                    except Exception:
                        cleaned[k] = v
            return cleaned
    except Exception as e:
        print(f"Error fetching raw {doc_type}: {e}")
    return {}

def fetch_resolved_document_data(shipment_id: str, doc_type: str) -> dict:
    data = fetch_document_raw(shipment_id, doc_type)
    if not data:
        return {}

    if "items" in data:
        data["items"] = ensure_list(data["items"])

    overridden_fields = set()

    query = f"""
    SELECT field_name, audited_value
    FROM `{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl`
    WHERE shipment_id = @shipment_id AND document_type = @doc_type
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("shipment_id", "STRING", shipment_id),
            bigquery.ScalarQueryParameter("doc_type", "STRING", doc_type)
        ]
    )
    try:
        df = bq_client.query(query, job_config=job_config).to_dataframe()
        for _, row in df.iterrows():
            field = row['field_name']
            val_str = row['audited_value']
            overridden_fields.add(field)
            
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
        print(f"Error fetching overrides for {doc_type}: {e}")

    if doc_type == "SLI" and "items" in data:
        items_list = ensure_list(data["items"])
        if items_list:
            if len(items_list) == 1 and isinstance(items_list[0], dict):
                if "total_value_usd" in overridden_fields and "items_0_value_usd" not in overridden_fields:
                    items_list[0]["value_usd"] = data["total_value_usd"]
                if "gross_weight_kg" in overridden_fields and "items_0_gross_weight_kg" not in overridden_fields:
                    items_list[0]["gross_weight_kg"] = data["gross_weight_kg"]
                if "net_weight_kg" in overridden_fields and "items_0_net_weight_kg" not in overridden_fields:
                    items_list[0]["net_weight_kg"] = data["net_weight_kg"]

            if "total_value_usd" not in overridden_fields:
                val_sum = sum(float(it.get("value_usd", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
                if val_sum > 0:
                    data["total_value_usd"] = val_sum

            if "gross_weight_kg" not in overridden_fields:
                gw_sum = sum(float(it.get("gross_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
                if gw_sum > 0:
                    data["gross_weight_kg"] = gw_sum

            if "net_weight_kg" not in overridden_fields:
                nw_sum = sum(float(it.get("net_weight_kg", 0.0) or 0.0) for it in items_list if isinstance(it, dict))
                if nw_sum > 0:
                    data["net_weight_kg"] = nw_sum

    return data

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
                    # Generate updated PDF passing full raw and resolved document data
                    original_data = fetch_document_raw(shipment_id, doc_type)
                    audited_data = fetch_resolved_document_data(shipment_id, doc_type)
                    new_pdf_bytes = pdf_generator.generate_audited_pdf(
                        shipment_id,
                        doc_type,
                        audited_data,
                        original_data,
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

def batch_update_document_overrides(shipment_id: str, doc_type: str, overrides_json: str) -> str:
    """Apply multiple field/item overrides at once for a shipment document in BigQuery
    and re-generate the stamp-certified audited PDF certificate.
    Use this tool whenever you need to update multiple line items (e.g. adding $2 to the first 47 items)
    or multiple fields on a document at the same time!
    
    Args:
        shipment_id: Shipment ID (e.g. '10385992').
        doc_type: Document type ('SLI', 'CIV', 'PKL', 'VGM').
        overrides_json: A JSON string dictionary mapping field names or line-item fields to new audited values,
                        OR a JSON string object with a batch instruction like:
                        '{"items_0_value_usd": "283.30", "items_1_value_usd": "283.30", ..., "total_value_usd": "96106.00"}'
                        OR '{"add_amount_per_item": 2.0, "start_index": 0, "end_index": 46, "target_field": "value_usd"}'
    """
    try:
        doc_type = doc_type.upper()
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        
        # Parse JSON
        parsed = json.loads(overrides_json) if isinstance(overrides_json, str) else overrides_json
        
        # Fetch current raw document data
        raw_doc = fetch_document_raw(shipment_id, doc_type)
        if not raw_doc:
            return f"Error: Document {doc_type} not found for shipment {shipment_id}."
            
        items = ensure_list(raw_doc.get("items", []))
        insert_rows = []
        
        # Check if it's a batch delta instruction (e.g. add $2 to first 47 items)
        if isinstance(parsed, dict) and "add_amount_per_item" in parsed:
            delta = float(parsed.get("add_amount_per_item", 0.0))
            start_idx = int(parsed.get("start_index", 0))
            end_idx = int(parsed.get("end_index", len(items) - 1))
            target_field = parsed.get("target_field", "value_usd")
            
            for idx in range(start_idx, min(end_idx + 1, len(items))):
                item = items[idx] if idx < len(items) and isinstance(items[idx], dict) else {}
                orig_val = float(item.get(target_field, 0.0) or 0.0)
                audited_val = orig_val + delta
                field_name = f"items_{idx}_{target_field}"
                insert_rows.append({
                    "shipment_id": shipment_id,
                    "document_type": doc_type,
                    "field_name": field_name,
                    "original_value": str(orig_val),
                    "audited_value": str(round(audited_val, 2)),
                    "updated_at": now_ts
                })
            
            # Recalculate package total sum if applicable
            if doc_type == "SLI" and target_field == "value_usd":
                orig_total = float(raw_doc.get("total_value_usd", 0.0) or 0.0)
                new_total = orig_total + (delta * (min(end_idx + 1, len(items)) - start_idx))
                insert_rows.append({
                    "shipment_id": shipment_id,
                    "document_type": doc_type,
                    "field_name": "total_value_usd",
                    "original_value": str(orig_total),
                    "audited_value": str(round(new_total, 2)),
                    "updated_at": now_ts
                })
        
        elif isinstance(parsed, dict):
            for field_name, audited_val in parsed.items():
                orig_val = str(raw_doc.get(field_name, ""))
                insert_rows.append({
                    "shipment_id": shipment_id,
                    "document_type": doc_type,
                    "field_name": field_name,
                    "original_value": orig_val,
                    "audited_value": str(audited_val),
                    "updated_at": now_ts
                })
        
        if insert_rows:
            table_id = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
            load_job = bq_client.load_table_from_json(insert_rows, table_id)
            load_job.result()
            
        # Re-generate audited PDF using full resolved document data
        pdf_status = "No PDF generator available"
        if pdf_generator and hasattr(pdf_generator, 'generate_audited_pdf'):
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
                original_data = fetch_document_raw(shipment_id, doc_type)
                audited_data = fetch_resolved_document_data(shipment_id, doc_type)
                
                new_pdf_bytes = pdf_generator.generate_audited_pdf(
                    shipment_id,
                    doc_type,
                    audited_data,
                    original_data,
                    original_pdf_bytes
                )
                if new_pdf_bytes:
                    orig_name = target_blob.name
                    audited_name = orig_name if "_audited" in orig_name.lower() else (orig_name[:-4] + "_audited.pdf")
                    out_blob = bucket.blob(audited_name)
                    out_blob.upload_from_string(new_pdf_bytes, content_type="application/pdf")
                    pdf_status = f"Audited PDF generated and uploaded to GCS as {audited_name}"

        return json.dumps({
            "status": "success",
            "shipment_id": shipment_id,
            "document_type": doc_type,
            "overrides_applied_count": len(insert_rows),
            "message": f"Successfully applied batch overrides ({len(insert_rows)} fields) on {doc_type} for shipment {shipment_id}.",
            "pdf_status": pdf_status
        }, indent=2)
    except Exception as e:
        return f"Error in batch_update_document_overrides: {e}"

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
    
    STRICT SOURCE OF TRUTH RULES ENFORCED:
    - Commercial Invoice (CIV) is ALWAYS Truth for financial/cost values. NEVER edit CIV! Edit SLI.
    - Packing List (PKL) is ALWAYS Truth for weight values. NEVER edit PKL! Edit SLI or VGM.
    """
    try:
        anom_str = fetch_shipment_anomalies(shipment_id)
        data = json.loads(anom_str)
        anomalies = data.get("anomalies", [])
        
        if not anomalies:
            return json.dumps({
                "status": "info",
                "message": f"Shipment {shipment_id} has no recorded anomalies in BigQuery to resolve."
            })

        resolutions = []
        raw_sli = fetch_document_raw(shipment_id, "SLI")
        sli_items = ensure_list(raw_sli.get("items", [])) if raw_sli else []
        is_multi_item = len(sli_items) > 1
        
        discrepancy_summaries = []
        
        for a in anomalies:
            cat = a.get("discrepancy_category", "")
            field = a.get("field_flagged", "")
            exp_val = a.get("expected_value")
            act_val = a.get("actual_value")

            target_doc = "SLI"
            target_field = "total_value_usd"
            target_val = str(exp_val) if exp_val is not None else str(act_val)

            if "weight" in cat.lower() or "weight" in field.lower():
                target_doc = "SLI"
                is_net = "net" in field.lower()
                target_field = "net_weight_kg" if is_net else "gross_weight_kg"
                label = "Net Weight" if is_net else "Gross Weight"
                
                if is_multi_item:
                    discrepancy_summaries.append(
                        f"**{label} Discrepancy**: SLI {label.lower()} total is **{act_val} kg**, which differs from Packing List (PKL) source of truth total of **{exp_val} kg**."
                    )
                else:
                    res = save_field_override(shipment_id, target_doc, target_field, target_val)
                    resolutions.append({"category": cat, "document": target_doc, "field": target_field, "value_applied": target_val, "result": res})
            elif "financial" in cat.lower() or "amount" in field.lower() or "value" in field.lower():
                target_doc = "SLI"
                if is_multi_item and exp_val is not None and act_val is not None:
                    try:
                        exp_f = float(exp_val)
                        act_f = float(act_val)
                        diff = round(exp_f - act_f, 2)
                        diff_str = f"+${diff:,.2f}" if diff > 0 else f"-${abs(diff):,.2f}"
                        discrepancy_summaries.append(
                            f"**Financial Discrepancy**: SLI line items total **${act_f:,.2f}**, which differs from Commercial Invoice (CIV) source of truth total of **${exp_f:,.2f}** (difference of **{diff_str}**)."
                        )
                    except Exception:
                        res = save_field_override(shipment_id, target_doc, "total_value_usd", target_val)
                        resolutions.append({"category": cat, "document": target_doc, "field": target_field, "value_applied": target_val, "result": res})
                else:
                    res = save_field_override(shipment_id, target_doc, "total_value_usd", target_val)
                    resolutions.append({"category": cat, "document": target_doc, "field": target_field, "value_applied": target_val, "result": res})
            else:
                res = save_field_override(shipment_id, target_doc, target_field, target_val)
                resolutions.append({"category": cat, "document": target_doc, "field": target_field, "value_applied": target_val, "result": res})

        if is_multi_item and discrepancy_summaries:
            has_gw = any("Gross Weight Discrepancy" in s for s in discrepancy_summaries)
            has_nw = any("Net Weight Discrepancy" in s for s in discrepancy_summaries)
            has_fin = any("Financial Discrepancy" in s for s in discrepancy_summaries)
            
            examples = []
            if has_gw:
                examples.append("'Add 15 kg to item #1 gross weight'")
            if has_nw:
                examples.append("'Add 11.7 kg to item #1 net weight'")
            if has_fin:
                examples.append("'Add $30 to item #1 value'")
                
            if not examples:
                examples.append("'Add 1 kg to item #1 gross weight, or add $2 to item #1 value'")
                
            eg_str = "e.g. " + ", or ".join(examples)

            summary_list = "\n".join(f"• {s}" for s in discrepancy_summaries)
            user_input_prompt = (
                f"Shipment #{shipment_id} contains **{len(sli_items)} line items** on the SLI with the following discrepancy flags:\n"
                f"{summary_list}\n\n"
                f"Because this shipment contains multiple line items, please specify how you would like the line items adjusted ({eg_str})."
            )
            return json.dumps({
                "status": "requires_user_specification",
                "shipment_id": shipment_id,
                "prompt_user": user_input_prompt,
                "resolutions": resolutions
            }, indent=2)

        return json.dumps({
            "status": "success",
            "shipment_id": shipment_id,
            "message": f"Autonomously resolved discrepancy flag(s) for shipment {shipment_id} adhering to Source of Truth rules (CIV = Price Truth, PKL = Weight Truth).",
            "resolutions": resolutions
        }, indent=2)
    except Exception as e:
        return f"Error in auto_resolve_shipment_discrepancies: {e}"

def query_foreign_currency_shipments() -> str:
    """Query BigQuery for all shipments that use foreign currencies (e.g. EUR, CAD, GBP, JPY) instead of USD.
    Returns shipment IDs, document type, and foreign currency used.
    """
    query = f"""
    WITH Currencies AS (
        SELECT shipment_id, 'CIV' as doc_type, UPPER(TRIM(currency)) AS currency FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl` WHERE currency IS NOT NULL
        UNION ALL
        SELECT shipment_id, 'SLI' as doc_type, UPPER(TRIM(currency)) AS currency FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl` WHERE currency IS NOT NULL
    )
    SELECT shipment_id, STRING_AGG(DISTINCT doc_type, ', ') as docs, ARRAY_AGG(currency ORDER BY currency LIMIT 1)[OFFSET(0)] as foreign_currency
    FROM Currencies
    WHERE currency NOT IN ('USD', '$', '')
    GROUP BY shipment_id
    """
    try:
        df = bq_client.query(query).to_dataframe()
        if df.empty:
            return json.dumps({"status": "success", "message": "No foreign currency shipments found.", "shipments": []})
        records = df.to_dict(orient="records")
        return json.dumps({"status": "success", "count": len(records), "shipments": records}, indent=2)
    except Exception as e:
        return f"Error querying foreign currency shipments: {e}"

def query_zero_dollar_item_shipments() -> str:
    """Query BigQuery for all shipments that contain zero-dollar ($0) line items across CIV and SLI documents.
    Returns shipment IDs, material numbers, HTS codes, and item counts.
    """
    query = f"""
    WITH CivZeroItems AS (
        SELECT 
            shipment_id,
            'CIV' as doc_type,
            COALESCE(item.material_number, 'Unknown') AS material_number,
            COALESCE(item.hts_code, 'Unassigned HTS') AS hts_code,
            COALESCE(item.total_value, item.unit_price) AS val
        FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl`,
        UNNEST(items) AS item
        WHERE COALESCE(item.total_value, item.unit_price) = 0.0
    ),
    SliZeroItems AS (
        SELECT 
            shipment_id,
            'SLI' as doc_type,
            'Unknown' AS material_number,
            'Unassigned HTS' AS hts_code,
            item.value_usd AS val
        FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl`,
        UNNEST(items) AS item
        WHERE item.value_usd = 0.0
    ),
    AllZeroItems AS (
        SELECT * FROM CivZeroItems
        UNION ALL
        SELECT * FROM SliZeroItems
    )
    SELECT 
        shipment_id,
        STRING_AGG(DISTINCT doc_type, ', ') as doc_types,
        COUNT(*) as zero_dollar_items_count,
        STRING_AGG(DISTINCT material_number, ', ') as material_numbers,
        STRING_AGG(DISTINCT hts_code, ', ') as hts_codes
    FROM AllZeroItems
    GROUP BY shipment_id
    """
    try:
        df = bq_client.query(query).to_dataframe()
        if df.empty:
            return json.dumps({"status": "success", "message": "No zero-dollar item shipments found.", "shipments": []})
        records = df.to_dict(orient="records")
        return json.dumps({"status": "success", "count": len(records), "shipments": records}, indent=2)
    except Exception as e:
        return f"Error querying zero-dollar item shipments: {e}"

def query_shipments_by_custom_filter(filter_prompt: str) -> str:
    """Query BigQuery across all shipments to answer general user inquiries (e.g. 'Show all shipments with more than 20 items', 'Which shipments have weight discrepancies', 'List shipments with total USD > 50000').
    Returns a structured list of matching shipments and their item counts, values, weights, and anomaly flags.
    """
    query = f"""
    WITH SliSummary AS (
        SELECT 
            shipment_id,
            total_value_usd,
            gross_weight_kg,
            net_weight_kg,
            ARRAY_LENGTH(items) AS sli_items_count
        FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl`
    ),
    CivSummary AS (
        SELECT 
            shipment_id,
            total_amount,
            currency,
            ARRAY_LENGTH(items) AS civ_items_count
        FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl`
    ),
    PklSummary AS (
        SELECT 
            shipment_id,
            gross_weight_kg,
            net_weight_kg
        FROM `{PROJECT_ID}.{DATASET_ID}.PKL_Tbl`
    ),
    AnomSummary AS (
        SELECT 
            shipment_id,
            STRING_AGG(DISTINCT discrepancy_category, ', ') AS anomaly_categories,
            COUNT(*) AS anomaly_count
        FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl`
        GROUP BY shipment_id
    )
    SELECT 
        COALESCE(s.shipment_id, c.shipment_id, p.shipment_id) AS shipment_id,
        COALESCE(s.sli_items_count, c.civ_items_count, 0) AS line_items_count,
        s.total_value_usd AS sli_total_value_usd,
        c.total_amount AS civ_total_amount,
        c.currency,
        s.gross_weight_kg AS sli_gross_weight_kg,
        p.gross_weight_kg AS pkl_gross_weight_kg,
        COALESCE(a.anomaly_categories, 'Clean / No Anomalies') AS anomaly_status,
        COALESCE(a.anomaly_count, 0) AS anomaly_count
    FROM SliSummary s
    FULL OUTER JOIN CivSummary c ON s.shipment_id = c.shipment_id
    FULL OUTER JOIN PklSummary p ON s.shipment_id = p.shipment_id
    LEFT JOIN AnomSummary a ON COALESCE(s.shipment_id, c.shipment_id, p.shipment_id) = a.shipment_id
    ORDER BY line_items_count DESC
    """
    try:
        df = bq_client.query(query).to_dataframe()
        if df.empty:
            return json.dumps({"status": "success", "message": "No shipments found in BigQuery.", "shipments": []})
        
        records = df.to_dict(orient="records")
        return json.dumps({
            "status": "success",
            "filter_prompt": filter_prompt,
            "total_shipments_in_db": len(records),
            "shipments": records
        }, indent=2, default=str)
    except Exception as e:
        return f"Error querying BigQuery for general shipment filter: {e}"




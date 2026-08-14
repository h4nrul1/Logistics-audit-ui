import os
import sys
import json
import time
import base64
import datetime
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
import pandas as pd
from google.cloud import bigquery, storage
try:
    from google.cloud import run_v2
except ImportError:
    run_v2 = None

# Add directories to sys.path so modules can be imported cleanly
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(BACKEND_DIR))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import pdf_generator
except ImportError:
    pdf_generator = None

PROJECT_ID = os.getenv("PROJECT_ID", "it-ai-briggs-agentspace")
DATASET_ID = os.getenv("DATASET_ID", "logistics_dataset")
BUCKET_NAME = os.getenv("BUCKET_NAME", "logistic-audit-pdfs")

app = FastAPI(title="Logistics Audit API", version="2.0.0")

@app.get("/health")
@app.get("/healthz")
@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Logistics Audit API", "version": "2.0.0"}

# Enable CORS for local React Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bq_client = bigquery.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)

# Helper Data Structures
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

def normalize_field_name(field):
    return field.lower().replace(" ", "").replace("_", "").replace("(", "").replace(")", "").replace(":", "")

# In-Memory Cache for Instant UI Responses
cache_store = {
    "queue": {"data": None, "ts": 0},
    "anomalies": {"data": None, "ts": 0},
    "indicators": {"data": None, "ts": 0}
}

def get_all_anomalies():
    now = time.time()
    if cache_store["anomalies"]["data"] is not None and now - cache_store["anomalies"]["ts"] < 30:
        return cache_store["anomalies"]["data"]
    
    query = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl`"
    try:
        df = bq_client.query(query).to_dataframe()
        cache_store["anomalies"]["data"] = df
        cache_store["anomalies"]["ts"] = now
        return df
    except Exception as e:
        print(f"Error fetching anomalies: {e}")
        return pd.DataFrame()

def get_all_indicators():
    now = time.time()
    if cache_store["indicators"]["data"] is not None and now - cache_store["indicators"]["ts"] < 30:
        return cache_store["indicators"]["data"]
        
    query = f"""
    WITH Currencies AS (
        SELECT shipment_id, UPPER(TRIM(currency)) AS currency FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl` WHERE currency IS NOT NULL
        UNION ALL
        SELECT shipment_id, UPPER(TRIM(currency)) AS currency FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl` WHERE currency IS NOT NULL
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
        FROM `{PROJECT_ID}.{DATASET_ID}.CIV_Tbl`,
        UNNEST(items) AS item
    ),
    SliItems AS (
        SELECT 
            shipment_id,
            'Unknown Material' AS material,
            'Unassigned HTS' AS hts_code,
            item.value_usd AS val
        FROM `{PROJECT_ID}.{DATASET_ID}.SLI_Tbl`,
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
        df = bq_client.query(query).to_dataframe()
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
                    hts = str(row["hts_code"])
                    cnt = int(row["zero_count"])
                    total_zero += cnt
                    mats = [m.strip() for m in str(row["materials"]).split(",") if m.strip()]
                    hts_groups[hts] = {"count": cnt, "materials": mats}

            indicators_map[sid] = {
                "currency": currency,
                "zero_count": total_zero,
                "hts_groups": hts_groups
            }
        cache_store["indicators"]["data"] = indicators_map
        cache_store["indicators"]["ts"] = now
        return indicators_map
    except Exception as e:
        print(f"Error fetching indicators: {e}")
        return {}

def fetch_document_raw(shipment_id: str, doc_type: str) -> Dict[str, Any]:
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

def fetch_resolved_document_data(shipment_id: str, doc_type: str) -> Dict[str, Any]:
    data = fetch_document_raw(shipment_id, doc_type)
    if not data:
        return {}

    if "items" in data:
        data["items"] = ensure_list(data["items"])

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

def get_resolved_overrides_set():
    query = f"SELECT DISTINCT shipment_id FROM `{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl` WHERE document_type = 'COMPLIANCE' AND audited_value = 'Resolved'"
    try:
        df = bq_client.query(query).to_dataframe()
        if not df.empty:
            return set(df['shipment_id'].unique())
    except Exception:
        pass
    return set()

# REST Endpoints
@app.get("/api/queue")
def get_master_queue():
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"BigQuery Query Error: {e}")

    anomalies_df = get_all_anomalies()
    failed_shipment_ids = set()
    if not anomalies_df.empty and "shipment_id" in anomalies_df.columns:
        failed_shipment_ids = set(anomalies_df['shipment_id'].unique())

    resolved_shipment_ids = get_resolved_overrides_set()
    indicators_map = get_all_indicators()

    all_shipment_data = df.to_dict(orient="records") if not df.empty else []
    all_shipment_ids_in_data = {row['shipment_id'] for row in all_shipment_data}
    if not anomalies_df.empty:
        missing_ids = set(anomalies_df['shipment_id'].unique()) - all_shipment_ids_in_data
        for missing_id in missing_ids:
            all_shipment_data.append({'shipment_id': missing_id, 'processed_at': None})

    queue_data = []
    for row in all_shipment_data:
        sid = str(row['shipment_id'])
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

        ind = indicators_map.get(sid, {"currency": None, "zero_count": 0, "hts_groups": {}})
        parts = []
        if ind["currency"]:
            parts.append(f"💱 {ind['currency']}")
        if ind["zero_count"] > 0:
            cnt = ind["zero_count"]
            parts.append(f"🏷️ {cnt} ($0 item)" if cnt == 1 else f"🏷️ {cnt} ($0 items)")
        indicator_str = " | ".join(parts) if parts else "None"

        queue_data.append({
            "shipment_id": sid,
            "status": status,
            "categories": categories_str,
            "indicators": indicator_str,
            "processed_at": row.get('processed_at')
        })

    return {"shipments": queue_data}

@app.get("/api/shipments/{shipment_id}")
def get_shipment_detail(shipment_id: str):
    anomalies_df = get_all_anomalies()
    shipment_anoms = []
    if not anomalies_df.empty:
        df_sub = anomalies_df[anomalies_df['shipment_id'] == shipment_id]
        if not df_sub.empty:
            shipment_anoms = df_sub.to_dict(orient="records")

    documents = {}
    for dt in ["CIV", "PKL", "SLI", "VGM"]:
        data = fetch_resolved_document_data(shipment_id, dt)
        if data:
            documents[dt] = data

    indicators_map = get_all_indicators()
    ind = indicators_map.get(shipment_id, {"currency": None, "zero_count": 0, "hts_groups": {}})

    prefix = f"shipment_{shipment_id}/"
    pdf_files = []
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))
        for b in blobs:
            if b.name.lower().endswith('.pdf'):
                pdf_files.append({
                    "name": b.name.split('/')[-1],
                    "blob_name": b.name,
                    "updated": b.updated.isoformat() if b.updated else None,
                    "is_audited": "_audited" in b.name.lower()
                })
    except Exception as e:
        print(f"GCS List Error: {e}")

    # Check for compliance marker or audited field overrides
    has_compliance_marker = False
    has_any_overrides = False
    try:
        df_comp = bq_client.query(f"SELECT document_type FROM `{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl` WHERE shipment_id = '{shipment_id}'").to_dataframe()
        if not df_comp.empty:
            has_any_overrides = True
            if "COMPLIANCE" in df_comp['document_type'].values:
                has_compliance_marker = True
    except Exception:
        pass

    has_anomalies = len(shipment_anoms) > 0
    has_audited_pdfs = any(p.get("is_audited") for p in pdf_files)

    if has_compliance_marker and not has_anomalies:
        status_str = "Resolved"
        is_resolved = True
        is_pending_compliance = False
    elif has_anomalies:
        status_str = "Failed"
        is_resolved = False
        is_pending_compliance = False
    elif has_any_overrides or has_audited_pdfs:
        status_str = "Audited / Pending Compliance"
        is_resolved = False
        is_pending_compliance = True
    else:
        status_str = "Passed"
        is_resolved = False
        is_pending_compliance = False

    return {
        "shipment_id": shipment_id,
        "status": status_str,
        "is_resolved": is_resolved,
        "is_pending_compliance": is_pending_compliance,
        "documents": documents,
        "anomalies": shipment_anoms,
        "indicators": ind,
        "pdf_files": pdf_files
    }

@app.get("/api/shipments/{shipment_id}/pdf")
def stream_pdf(shipment_id: str, blob_name: str):
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(blob_name)
        pdf_bytes = blob.download_as_bytes()
        return Response(content=pdf_bytes, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"PDF not found: {e}")

class OverridesRequest(BaseModel):
    overrides: Dict[str, Dict[str, Any]]

@app.post("/api/shipments/{shipment_id}/overrides")
def save_shipment_overrides(shipment_id: str, payload: OverridesRequest):
    overrides = payload.overrides
    if not overrides:
        return {"status": "ok", "message": "No changes to save."}

    cache_store["queue"]["data"] = None
    cache_store["anomalies"]["data"] = None
    cache_store["indicators"]["data"] = None

    modified_docs = []
    for doc_type, changed_vals in overrides.items():
        if not changed_vals:
            continue
        
        orig_vals = fetch_resolved_document_data(shipment_id, doc_type)
        if not orig_vals:
            continue

        insert_rows = []
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        for field, val in changed_vals.items():
            orig_v = orig_vals.get(field, "")
            insert_rows.append({
                "shipment_id": shipment_id,
                "document_type": doc_type,
                "field_name": field,
                "original_value": str(orig_v),
                "audited_value": str(val),
                "updated_at": now_ts
            })

        if insert_rows:
            table_id = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
            try:
                load_job = bq_client.load_table_from_json(insert_rows, table_id)
                load_job.result()
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"BigQuery Insert Overrides Load Job Error: {e}")

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
                        modified_docs.append(doc_type)
            except Exception as e:
                print(f"PDF Gen Error for {doc_type}: {e}")
                import traceback
                traceback.print_exc()

    return {"status": "success", "modified_documents": modified_docs}

@app.delete("/api/shipments/{shipment_id}/overrides/{doc_type}")
def reset_shipment_override(shipment_id: str, doc_type: str):
    table_id = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
    doc_clause = f"document_type = '{doc_type}'" if doc_type.upper() != "ALL" else "1=1"
    
    delete_query = f"""
    DELETE FROM `{table_id}`
    WHERE shipment_id = '{shipment_id}' AND {doc_clause}
    """
    try:
        query_job = bq_client.query(delete_query)
        query_job.result()
    except Exception as e:
        if "streaming buffer" in str(e).lower():
            try:
                # Streaming buffer fallback
                select_query = f"SELECT * FROM `{table_id}` WHERE NOT (shipment_id = '{shipment_id}' AND {doc_clause})"
                df = bq_client.query(select_query).to_dataframe()
                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                bq_client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
            except Exception as inner_e:
                raise HTTPException(status_code=500, detail=f"BigQuery Delete Fallback Error: {inner_e}")
        else:
            raise HTTPException(status_code=500, detail=f"BigQuery Delete Overrides Error: {e}")

    # Delete audited PDF blob(s) from GCS
    try:
        prefix = f"shipment_{shipment_id}/"
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))
        for b in blobs:
            if b.name.lower().endswith('.pdf') and "_audited" in b.name.lower():
                if doc_type.upper() == "ALL" or doc_type.lower() in b.name.lower():
                    b.delete()
                    print(f"Deleted audited blob: {b.name}")
    except Exception as e:
        print(f"Error deleting audited blob for {doc_type}: {e}")

    # Clear server memory caches
    cache_store["queue"]["data"] = None
    cache_store["anomalies"]["data"] = None
    cache_store["indicators"]["data"] = None

    return {"status": "success", "message": f"Reset {doc_type} corrections successfully."}

@app.post("/api/shipments/{shipment_id}/resolve")
def resolve_shipment_compliance(shipment_id: str):
    """Flags a shipment as manually confirmed compliant / resolved in BigQuery anomalies table."""
    delete_query = f"""
    DELETE FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl`
    WHERE shipment_id = '{shipment_id}'
    """
    try:
        query_job = bq_client.query(delete_query)
        query_job.result()
    except Exception as e:
        if "streaming buffer" in str(e).lower():
            try:
                select_query = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl` WHERE shipment_id != '{shipment_id}'"
                df = bq_client.query(select_query).to_dataframe()
                job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
                table_id = f"{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl"
                bq_client.load_table_from_dataframe(df, table_id, job_config=job_config).result()
            except Exception as inner_e:
                print(f"Resolve streaming buffer fallback warning: {inner_e}")
        else:
            print(f"Error flagging shipment compliance: {e}")

    # Mark in Audited_Overrides_Tbl so shipment status is tracked as 'Resolved'
    override_table = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
    row = [{
        "shipment_id": shipment_id,
        "document_type": "COMPLIANCE",
        "field_name": "status",
        "original_value": "Failed",
        "audited_value": "Resolved",
        "updated_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }]
    try:
        load_job = bq_client.load_table_from_json(row, override_table)
        load_job.result()
    except Exception as e:
        print(f"Error inserting compliance override: {e}")

    cache_store["queue"]["data"] = None
    cache_store["anomalies"]["data"] = None
    cache_store["indicators"]["data"] = None

    return {"status": "success", "shipment_id": shipment_id, "message": "Shipment flagged as compliant / resolved."}

@app.post("/api/shipments/{shipment_id}/reopen")
def reopen_shipment_audit(shipment_id: str):
    """Re-opens audit for a shipment, removing compliance marker and restoring anomaly tracking in BigQuery."""
    # 1. Remove COMPLIANCE override marker
    override_table = f"{PROJECT_ID}.{DATASET_ID}.Audited_Overrides_Tbl"
    del_override = f"DELETE FROM `{override_table}` WHERE shipment_id = '{shipment_id}' AND document_type = 'COMPLIANCE'"
    try:
        bq_client.query(del_override).result()
    except Exception as e:
        print(f"Error removing compliance override marker: {e}")

    # 2. Re-insert manual anomaly flag into Shipment_Anomalies_Tbl so UI tracks it as failed/open
    table_id = f"{PROJECT_ID}.{DATASET_ID}.Shipment_Anomalies_Tbl"
    row = [{
        "shipment_id": shipment_id,
        "discrepancy_category": "Manual Audit Re-opened",
        "field_flagged": "status",
        "expected_value": "Under Auditor Review",
        "actual_value": "Re-opened for Editing",
        "processed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }]
    try:
        load_job = bq_client.load_table_from_json(row, table_id)
        load_job.result()
    except Exception as e:
        print(f"Error re-opening shipment audit in BQ: {e}")

    cache_store["queue"]["data"] = None
    cache_store["anomalies"]["data"] = None
    cache_store["indicators"]["data"] = None

    return {"status": "success", "shipment_id": shipment_id, "message": "Shipment audit re-opened successfully."}

@app.post("/api/sync")
def trigger_sync():
    try:
        client = run_v2.JobsClient()
        job_name = client.job_path(
            project=PROJECT_ID,
            location="us-central1",
            job="shipment-ingestion-job"
        )
        request = run_v2.RunJobRequest(name=job_name)
        operation = client.run_job(request=request)
        return {"status": "success", "message": "Ingestion sync job triggered successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering sync job: {e}")

# --- Auth & Agent Session Endpoints ---

try:
    from web_app.backend.auth import extract_user_from_request
    from web_app.backend.agent.memory import (
        get_user_sessions,
        create_user_session,
        get_session_messages,
        delete_user_session,
        add_session_message,
    )
    from web_app.backend.agent.runner import run_agent_turn
except ImportError:
    from auth import extract_user_from_request
    from agent.memory import (
        get_user_sessions,
        create_user_session,
        get_session_messages,
        delete_user_session,
        add_session_message,
    )
    from agent.runner import run_agent_turn

@app.get("/api/auth/me")
def get_current_user(request: Request):
    user_info = extract_user_from_request(request)
    return user_info

@app.get("/api/agent/sessions")
def list_sessions(request: Request):
    user_info = extract_user_from_request(request)
    user_id = user_info["user_id"]
    sessions = get_user_sessions(user_id)
    return {"sessions": sessions}

class CreateSessionRequest(BaseModel):
    title: Optional[str] = ""

@app.post("/api/agent/sessions")
def create_session(request: Request, payload: CreateSessionRequest):
    user_info = extract_user_from_request(request)
    user_id = user_info["user_id"]
    title = payload.title or "New Audit Thread"
    session = create_user_session(user_id, title)
    return session

@app.get("/api/agent/sessions/{session_id}/messages")
def list_session_messages(session_id: str, request: Request):
    user_info = extract_user_from_request(request)
    user_id = user_info["user_id"]
    messages = get_session_messages(user_id, session_id)
    return {"messages": messages}

@app.delete("/api/agent/sessions/{session_id}")
def remove_session(session_id: str, request: Request):
    user_info = extract_user_from_request(request)
    user_id = user_info["user_id"]
    delete_user_session(user_id, session_id)
    return {"status": "success", "message": "Session deleted"}

class AgentChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = ""
    current_shipment_id: Optional[str] = ""

@app.post("/api/agent/chat")
def agent_chat(payload: AgentChatRequest, request: Request):
    user_info = extract_user_from_request(request)
    user_id = user_info["user_id"]
    
    session_id = payload.session_id
    if not session_id:
        session = create_user_session(user_id, f"Audit {payload.current_shipment_id or 'Thread'}")
        session_id = session["session_id"]

    # Save user message to persistent memory
    add_session_message(user_id, session_id, "user", payload.message)

    # Run agent turn
    prompt_text = payload.message
    if payload.current_shipment_id:
        prompt_text = f"[Active Canvas Context: Currently inspecting Shipment #{payload.current_shipment_id}]\n\n{payload.message}"

    result = run_agent_turn(prompt_text, session_id=session_id)
    
    agent_resp = result.get("response", "Task completed.")
    trajectory = result.get("trajectory", [])

    # Save agent response to persistent memory
    add_session_message(user_id, session_id, "agent", agent_resp, trajectory=trajectory)

    return {
        "status": "success",
        "session_id": session_id,
        "response": agent_resp,
        "trajectory": trajectory,
    }

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

frontend_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")
if not os.path.exists(frontend_dist):
    frontend_dist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")

if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="API endpoint not found")
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        index_file = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend dist index.html not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)

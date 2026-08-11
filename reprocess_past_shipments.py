import base64
import json
import time
import requests
import google.auth
from google.auth.transport.requests import Request
from google.cloud import bigquery, storage

PROJECT_ID = "it-ai-briggs-agentspace"
DATASET_ID = "logistics_dataset"
BUCKET_NAME = "logistic-audit-pdfs"
TOPIC_ID = "shipment-processing-trigger"

bq_client = bigquery.Client(project=PROJECT_ID)
storage_client = storage.Client(project=PROJECT_ID)

# Obtain auth credentials for Pub/Sub REST API publishing
credentials, _ = google.auth.default(
    scopes=['https://www.googleapis.com/auth/cloud-platform']
)

def publish_pubsub_payload(payload):
    if not credentials.valid:
        credentials.refresh(Request())
    
    url = f"https://pubsub.googleapis.com/v1/projects/{PROJECT_ID}/topics/{TOPIC_ID}:publish"
    message_bytes = json.dumps(payload).encode("utf-8")
    base64_data = base64.b64encode(message_bytes).decode("utf-8")
    
    headers = {
        "Authorization": f"Bearer {credentials.token}",
        "Content-Type": "application/json"
    }
    body = {
        "messages": [
            {"data": base64_data}
        ]
    }
    res = requests.post(url, headers=headers, json=body)
    res.raise_for_status()
    return res.json()

def reprocess_all_shipments():
    """
    Scans GCS bucket for all past shipment folders, fetches original processed_at timestamps 
    from BigQuery (or falls back to GCS file creation timestamps), truncates tables, 
    and re-triggers extractions preserving the original timestamps.
    """
    print("1. Fetching existing timestamps from BigQuery...")
    bq_timestamps = {}
    query = f"""
    SELECT shipment_id, CAST(MAX(processed_at) AS STRING) as original_processed_at
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
    """
    try:
        df = bq_client.query(query).to_dataframe()
        if not df.empty:
            bq_timestamps = dict(zip(df['shipment_id'], df['original_processed_at']))
    except Exception as e:
        print(f"Notice: Could not query BigQuery for existing timestamps ({e})")

    print("\n2. Discovering all shipment packages in GCS bucket...")
    bucket = storage_client.bucket(BUCKET_NAME)
    blobs = list(bucket.list_blobs())

    shipments = {}
    for b in blobs:
        if '/' in b.name:
            folder = b.name.split('/')[0]
            if folder.startswith('shipment_'):
                sid = folder.replace('shipment_', '')
                file_name = b.name.split('/')[-1]
                if not file_name:
                    continue
                if sid not in shipments:
                    # Use BigQuery timestamp if present, otherwise fallback to GCS file creation time
                    ts = bq_timestamps.get(sid, b.time_created.isoformat())
                    shipments[sid] = {
                        "processed_at": ts,
                        "files": {}
                    }
                shipments[sid]["files"][file_name] = f"gs://{BUCKET_NAME}/{b.name}"

    if not shipments:
        print("No shipments found in GCS bucket.")
        return

    print(f"Found {len(shipments)} shipment package(s) in GCS bucket to reprocess:")
    for sid, data in sorted(shipments.items()):
        print(f" - Shipment {sid}: {len(data['files'])} PDF file(s) (Timestamp: {data['processed_at']})")

    # 3. Truncate old tables
    print("\n3. Truncating old tables in BigQuery...")
    tables = ["CIV_Tbl", "PKL_Tbl", "SLI_Tbl", "VGM_Tbl", "Shipment_Anomalies_Tbl"]
    for tbl in tables:
        try:
            bq_client.query(f"TRUNCATE TABLE `{PROJECT_ID}.{DATASET_ID}.{tbl}`").result()
            print(f" - Truncated {tbl}")
        except Exception as e:
            print(f" - Failed to truncate {tbl}: {e}")
    print("Tables truncated successfully.")

    # 4. Re-publish triggers with original timestamps
    print("\n4. Re-publishing extraction triggers for all shipments...")
    for shipment_id, data in sorted(shipments.items()):
        payload = {
            "shipment_id": shipment_id,
            "processed_at": data["processed_at"],  # PRESERVED ORIGINAL TIMESTAMP
            "files": data["files"]
        }

        print(f"[{shipment_id}] Triggering re-extraction (Preserved Timestamp: {data['processed_at']})...")
        try:
            publish_pubsub_payload(payload)
            print(f"[{shipment_id}] Event published successfully.")
        except Exception as e:
            print(f"[{shipment_id}] Failed to publish event: {e}")
            
        time.sleep(2.5)

    print("\n--- All past shipments queued for re-extraction with original timestamps preserved! ---")

if __name__ == "__main__":
    reprocess_all_shipments()

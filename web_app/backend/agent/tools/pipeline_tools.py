import os
import sys
import json
from google.cloud import run_v2

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

root_dir = os.path.dirname(backend_dir)
if root_dir not in sys.path:
    sys.path.append(root_dir)

from agent.config import PROJECT_ID, LOCATION

def trigger_drive_ingestion_sync() -> str:
    """Trigger the Cloud Run ingestion job ('shipment-ingestion-job') to scan Google Drive,
    group new PDF documents by shipment ID, and upload them to GCS bucket for processing.
    """
    try:
        client = run_v2.JobsClient()
        job_name = client.job_path(
            project=PROJECT_ID,
            location=LOCATION,
            job="shipment-ingestion-job"
        )
        request = run_v2.RunJobRequest(name=job_name)
        operation = client.run_job(request=request)
        return json.dumps({
            "status": "success",
            "message": "Google Drive Ingestion Sync Job triggered successfully.",
            "operation_id": operation.operation.name if hasattr(operation, "operation") else "started"
        }, indent=2)
    except Exception as e:
        return f"Error triggering Cloud Run ingestion sync job: {e}"

def trigger_reprocess_all_shipments() -> str:
    """Scan GCS bucket for all past shipment packages and re-trigger extraction pipeline
    events via Pub/Sub while preserving their original historical timestamps.
    """
    try:
        import reprocess_past_shipments
        reprocess_past_shipments.reprocess_all_shipments()
        return json.dumps({
            "status": "success",
            "message": "Reprocessing pipeline triggered for all past shipments with preserved timestamps."
        }, indent=2)
    except Exception as e:
        return f"Error triggering shipment reprocessing: {e}"

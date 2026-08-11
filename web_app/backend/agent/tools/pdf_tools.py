import os
import sys
import json
from google.cloud import storage

backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from agent.config import PROJECT_ID, BUCKET_NAME

storage_client = storage.Client(project=PROJECT_ID)

def list_shipment_pdfs(shipment_id: str) -> str:
    """List all original and audited PDF files available in Google Cloud Storage for a specific shipment.
    
    Args:
        shipment_id: Shipment ID (e.g. '10351463').
    """
    try:
        prefix = f"shipment_{shipment_id}/"
        bucket = storage_client.bucket(BUCKET_NAME)
        blobs = list(bucket.list_blobs(prefix=prefix))
        pdf_files = []
        for b in blobs:
            if b.name.lower().endswith('.pdf'):
                pdf_files.append({
                    "file_name": b.name.split('/')[-1],
                    "blob_path": b.name,
                    "updated_at": b.updated.isoformat() if b.updated else None,
                    "is_audited": "_audited" in b.name.lower()
                })
        return json.dumps({
            "shipment_id": shipment_id,
            "pdf_count": len(pdf_files),
            "pdf_files": pdf_files
        }, indent=2)
    except Exception as e:
        return f"Error listing PDFs for shipment {shipment_id}: {e}"

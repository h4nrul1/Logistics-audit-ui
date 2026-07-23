import io
import json
import google.auth
from google.cloud import storage, pubsub_v1
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 1. Cloud Run Auth
SCOPES = ['https://www.googleapis.com/auth/drive']
creds, project_id = google.auth.default(scopes=SCOPES)

# Drive API service
drive_service = build('drive', 'v3', credentials=creds)

# Initialize Pub/Sub Publisher
publisher = pubsub_v1.PublisherClient()
PROJECT_ID = "it-ai-briggs-agentspace" 
TOPIC_ID = "shipment-processing-trigger" 
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

def transfer_drive_to_gcs(drive_file_id, file_name, bucket_name, gcs_destination_path):
    """Downloads from Drive and uploads to GCS. Returns the GCS URI."""
    try:
        print(f"Fetching {file_name} from Google Drive...")
        request = drive_service.files().get_media(fileId=drive_file_id)
        
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            
        file_buffer.seek(0)
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(gcs_destination_path)
        
        blob.upload_from_file(file_buffer, content_type='application/pdf')
        gcs_uri = f"gs://{bucket_name}/{gcs_destination_path}"
        
        return gcs_uri
    except Exception as e:
        print(f"An error occurred during transfer: {e}")
        return None

def get_files_in_folder(folder_id):
    """Scans a Google Drive folder and returns all PDFs."""
    query = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    results = drive_service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
    return results.get('files', [])

def move_file_in_drive(file_id, current_folder_id, destination_folder_id):
    """Moves files to processed folder."""
    try:
        drive_service.files().update(
            fileId=file_id,
            addParents=destination_folder_id,
            removeParents=current_folder_id,
            fields='id, parents'
        ).execute()
        print(f"Moved file ID {file_id} to Processed folder.")
    except Exception as e:
        print(f"Failed to move file in Drive: {e}")

def clear_gcs_folder(bucket_name, prefix):
    """Checks for existing files with the given prefix and deletes them."""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blobs = bucket.list_blobs(prefix=prefix)
    
    deleted_count = 0
    for blob in blobs:
        blob.delete()
        deleted_count += 1
        
    if deleted_count > 0:
        print(f"Found and deleted {deleted_count} existing file(s) for prefix '{prefix}'. Replacing with new upload...")

# ==========================================
# MAIN EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    import re
    from collections import defaultdict

    BUCKET_NAME = "logistic-audit-pdfs"
    DRIVE_FOLDER_ID = "1FOnW5J9k763udzfdxW9d8iPg15RQQq2f" 
    PROCESSED_FOLDER_ID = "1rAdbu6a9M8mvxdJCSXUduSfQ9RYPuY7u"
    
    drive_files = get_files_in_folder(DRIVE_FOLDER_ID)
    
    if not drive_files:
        print("No PDFs found in the target folder.")
    else:
        print(f"Found {len(drive_files)} files. Grouping by shipment...\n")
        
        # Dictionary to group files by shipment ID
        # Format: {"10351463": [file1, file2, ...]}
        shipments = defaultdict(list)
        for file in drive_files:
            # Looks for an underscore followed by exactly 8 digits (e.g., _10351463)
            match = re.search(r'_(\d{8})', file['name']) 
            if match:
                shipment_id = match.group(1)
                shipments[shipment_id].append(file)
            else:
                print(f"Skipping {file['name']}: Could not find 8-digit shipment ID.")

        # Evaluate each shipment group
        for shipment_id, docs in shipments.items():
            filenames = [d['name'].upper() for d in docs]
            
            # Check for the presence of the 3 mandatory documents [cite: 162]
            has_civ = any('CIV' in name for name in filenames)
            has_pkl = any('PKL' in name for name in filenames)
            has_sli = any('SLI' in name for name in filenames)
            
            if has_civ and has_pkl and has_sli:
                print(f"[{shipment_id}] Mandatory documents found. Starting transfer...")
                
                # Generate a universal processing timestamp for this batch
                processed_at = datetime.now(ZoneInfo("America/Chicago")).isoformat()
                
                # Clear existing folder in GCS if it exists (handles re-uploads)
                gcs_folder_prefix = f"shipment_{shipment_id}/"
                clear_gcs_folder(BUCKET_NAME, gcs_folder_prefix)
                
                files_dict = {} # To hold GCS URIs for the Pub/Sub payload
                
                # Loop through and transfer ONLY the files for this ready shipment
                for doc in docs:
                    file_name = doc['name']
                    drive_file_id = doc['id']
                    
                    gcs_path = f"{gcs_folder_prefix}{file_name}"
                    
                    # Upload to GCS and move in Drive using your existing functions
                    gcs_uri = transfer_drive_to_gcs(drive_file_id, file_name, BUCKET_NAME, gcs_path)
                    
                    if gcs_uri:
                        move_file_in_drive(drive_file_id, DRIVE_FOLDER_ID, PROCESSED_FOLDER_ID)
                        # Add to our dictionary (handles multiple CIVs perfectly)
                        files_dict[file_name] = gcs_uri
                
                # 3. THE TRIGGER: Send to Pub/Sub to wake up the AI extraction
                payload = {
                    "shipment_id": shipment_id,
                    "processed_at": processed_at, # Injected timestamp for tracking
                    "files": files_dict
                }
                
                print(f"[{shipment_id}] Triggering AI Extraction...")
                message_bytes = json.dumps(payload).encode("utf-8")
                future = publisher.publish(topic_path, data=message_bytes)
                future.result() # Forces the container to wait for a delivery receipt
                print(f"[{shipment_id}] Trigger sent successfully.\n")
                
            else:
                print(f"[{shipment_id}] Shipment incomplete. Waiting for remaining documents. Currently has: {filenames}")

        print("Ingestion and Triggering Complete!")
import asyncio
import json
import base64
import time
import functions_framework
from google.cloud import bigquery
from google import genai
from google.genai import types
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# 1. Initialize Clients
PROJECT_ID = "it-ai-briggs-agentspace" # Make sure this matches your GCP project
REGION = "us-central1"
DATASET_ID = f"{PROJECT_ID}.logistics_dataset"

# Initialize BigQuery Client
bq_client = bigquery.Client(project=PROJECT_ID)

# Initialize Gemini
client = genai.Client(vertexai=True, project=PROJECT_ID, location=REGION)
MODEL_ID = "gemini-2.5-pro"

# 2. Define the extraction schemas
civ_schema = {
    "type": "OBJECT",
    "properties": {
        "currency": {"type": "STRING"},
        "total_amount": {"type": "NUMBER"},
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "material_number": {"type": "STRING"},
                    "hts_code": {"type": "STRING"}
                }
            }
        }
    }
}

pkl_schema = {
    "type": "OBJECT",
    "properties": {
        "gross_weight_lb": {"type": "NUMBER"},
        "gross_weight_kg": {"type": "NUMBER"},
        "net_weight_lb": {"type": "NUMBER"},
        "net_weight_kg": {"type": "NUMBER"},
        "pallet_count": {"type": "NUMBER"},
        "loose_case_count": {"type": "NUMBER"},
        "material_numbers": {"type": "ARRAY", "items": {"type": "STRING"}}
    }
}

sli_schema = {
    "type": "OBJECT",
    "properties": {
        "currency": {"type": "STRING"},
        "items": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "value_usd": {"type": "NUMBER"},
                    "gross_weight_kg": {"type": "NUMBER"},
                    "net_weight_kg": {"type": "NUMBER"}
                }
            }
        },
        "total_value_usd": {"type": "NUMBER"},
        "gross_weight_kg": {"type": "NUMBER"},
        "net_weight_kg": {"type": "NUMBER"}
    }
}

vgm_schema = {
    "type": "OBJECT",
    "properties": {
        "gross_weight_lb": {"type": "NUMBER"},
        "gross_weight_kg": {"type": "NUMBER"}
    }
}

async def extract_from_document(doc_type: str, uri: str, prompt: str, schema: dict) -> dict:
    print(f"[{doc_type}] Starting extraction for {uri}...")
    
    # Define the document part
    document_part = types.Part.from_uri(file_uri=uri, mime_type="application/pdf")
    
    # Configuration
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=0.0  
    )
    
    # Execute async request
    response = await client.aio.models.generate_content(
        model=MODEL_ID,
        contents=[document_part, prompt],
        config=config
    )
    
    print(f"[{doc_type}] Extraction complete.")
    
    return {
        "type": doc_type,
        "json_data": response.text
    }

async def process_shipment_concurrently(shipment_id: str, document_uris: dict, processed_at: str):
    """Main orchestrator that fans out the 4 Gemini requests and gathers them."""
    print(f"--- Processing Shipment: {shipment_id} (Batch: {processed_at}) ---")
    
    prompts = {
        "CIV": (
            "Analyze the attached Commercial Invoice. Extract the 'TOTAL AMOUNT.' "
            "Also identify the 3-letter currency code for the amounts (e.g., 'USD', 'EUR', 'CAD', 'MXN', 'GBP', 'JPY'). Output 'USD' if standard dollar symbols or USD are indicated. "
            "Additionally, find the list under the column 'PART NUMBER DESCRIPTION'. Extract a complete list of all items, providing both the material number and its corresponding 'HTS' number for each."
        ),
        "PKL": (
            "Analyze the attached Packing List. Extract the value for '** Gross Weight' and '** Net Weight' in both pounds (LB) and kilogran(KG)."
            "Find the 'TOTALS' section and extract the numeric values for 'Pallet' and 'Loose case'. "
            "Finally, extract the complete list of all 'Material Numbers'"
        ),
        "SLI": (
            "Analyze the attached Shipper's Letter of Instructions (SLI)."
            "First, find the columns titled 'Gross Weight in KG' and 'Net Weight in KG' and sum them to extract root 'gross_weight_kg' and 'net_weight_kg' totals (or extract the printed totals if explicitly shown)."
            "Find the section containing 'Value in USD' and extract the grand total value as 'total_value_usd'. "
            "Also identify the 3-letter currency code (e.g., 'USD', 'EUR', 'CAD', 'MXN', 'GBP', 'JPY'). Output 'USD' if standard dollar symbols or USD are indicated. "
            "Next, extract each individual package line item in the 'items' array, providing its corresponding 'value_usd', 'gross_weight_kg', and 'net_weight_kg' individually."
        ),
        "VGM": (
            "Analyze the attached Verified Gross Mass (VGM) document, "
            "and extract the values for 'Gross Weight' in both kilogram (KG) and pounds (LB)."
        )
    }
    
    schemas = {
        "CIV": civ_schema,
        "PKL": pkl_schema,
        "SLI": sli_schema,
        "VGM": vgm_schema
    }
    
    tasks = []
    # document_uris now contains { "CIV_10351463_1.pdf": "gs://...", ... }
    for file_name, uri in document_uris.items():
        
        # Extract the prefix (e.g., "CIV" from "CIV_10351463_1.pdf")
        doc_type = file_name.split('_')[0].upper()
        
        # Only process if it matches one of our 4 known document types
        if doc_type in prompts:
            task = asyncio.create_task(
                extract_from_document(
                    doc_type=doc_type,  # Pass "CIV" so BigQuery gets the right label
                    uri=uri,
                    prompt=prompts[doc_type],
                    schema=schemas[doc_type]
                )
            )
            tasks.append(task)
        else:
            print(f"Skipping {file_name}: Unrecognized document type.")
    
    results = await asyncio.gather(*tasks)
    print(f"\n--- All documents for {shipment_id} processed! ---")
    
    # Route the data to BigQuery
    for result in results:
        doc_type = result['type']
        json_payload = result['json_data']
        
        try:
            # Parse the string from Gemini into a Python dictionary
            row_data = json.loads(json_payload)
            
            row_data["shipment_id"] = shipment_id 
            row_data["document_type"] = doc_type
            row_data["processed_at"] = processed_at  # Injecting the timestamp
            
            table_id = f"{DATASET_ID}.{doc_type}_Tbl"
            
            print(f"Inserting {doc_type} data into {table_id} using Load Job...")
            
            job_config = bigquery.LoadJobConfig(
                source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
            )
            
            # Helper for retrying BigQuery operations when rate limits are encountered
            def run_load():
                return bq_client.load_table_from_json([row_data], table_id, job_config=job_config)

            # Retry up to 5 times with backoff if rate limits occur
            for attempt in range(5):
                try:
                    load_job = run_load()
                    load_job.result()
                    break
                except Exception as ex:
                    if ("rateLimitExceeded" in str(ex) or "403" in str(ex)) and attempt < 4:
                        sleep_s = (attempt + 1) * 3
                        print(f"[{doc_type}] BigQuery rate limit hit. Retrying in {sleep_s}s (Attempt {attempt + 1}/5)...")
                        time.sleep(sleep_s)
                    else:
                        raise ex

            print(f"[{doc_type}] Successfully loaded into BigQuery.")
                
        except json.JSONDecodeError as e:
            print(f"[{doc_type}] Failed to parse JSON from Gemini: {e}")
            print(f"Raw output was: {json_payload}")

    print(f"Triggering BigQuery audit logic for {shipment_id}...")

   # Converted to f-string to inject the shipment_id and processed_at for isolation
    audit_query = f"""
    INSERT INTO `it-ai-briggs-agentspace.logistics_dataset.Shipment_Anomalies_Tbl` 
    (shipment_id, processed_at, discrepancy_category, field_flagged, expected_value, actual_value)

    WITH LatestPKLBase AS (
        SELECT * FROM `it-ai-briggs-agentspace.logistics_dataset.PKL_Tbl`
        WHERE shipment_id = '{shipment_id}'
        QUALIFY RANK() OVER(PARTITION BY shipment_id ORDER BY processed_at DESC) = 1
    ),
    LatestCIVBase AS (
        SELECT *, LOWER(COALESCE(currency, 'usd')) AS norm_currency 
        FROM `it-ai-briggs-agentspace.logistics_dataset.CIV_Tbl`
        WHERE shipment_id = '{shipment_id}'
        QUALIFY RANK() OVER(PARTITION BY shipment_id ORDER BY processed_at DESC) = 1
    ),
    LatestSLI AS (
        SELECT *, LOWER(COALESCE(currency, 'usd')) AS norm_currency 
        FROM `it-ai-briggs-agentspace.logistics_dataset.SLI_Tbl`
        WHERE shipment_id = '{shipment_id}'
        QUALIFY RANK() OVER(PARTITION BY shipment_id ORDER BY processed_at DESC) = 1
    ),
    LatestVGM AS (
        SELECT * FROM `it-ai-briggs-agentspace.logistics_dataset.VGM_Tbl`
        WHERE shipment_id = '{shipment_id}'
        QUALIFY RANK() OVER(PARTITION BY shipment_id ORDER BY processed_at DESC) = 1
    ),
    DistinctPKLMaterials AS (
        SELECT DISTINCT 
            shipment_id, 
            mat_num AS material_number
        FROM LatestPKLBase,
        UNNEST(material_numbers) AS mat_num
    ),
    DistinctCIVMaterials AS (
        SELECT DISTINCT 
            shipment_id, 
            item.material_number
        FROM LatestCIVBase,
        UNNEST(items) AS item
    ),
    AggregatedCIVs AS (
        SELECT 
            shipment_id,
            SUM(total_amount) AS combined_total_amount,
            MAX(norm_currency) AS norm_currency
        FROM LatestCIVBase
        GROUP BY shipment_id
    )

    -- Financial Discrepancies (Only flagged for USD shipments; foreign currencies bypass)
    SELECT 
        c.shipment_id,
        CAST('{processed_at}' AS TIMESTAMP) AS processed_at,
        'Financial' AS discrepancy_category,
        'Total Amount' AS field_flagged,
        CAST(ROUND(c.combined_total_amount) AS STRING) AS expected_value,
        CAST(ROUND(s.total_value_usd) AS STRING) AS actual_value
    FROM AggregatedCIVs c
    JOIN LatestSLI s 
        ON c.shipment_id = s.shipment_id
    WHERE ROUND(c.combined_total_amount) != ROUND(s.total_value_usd)
      AND (c.norm_currency IN ('usd', '$') AND s.norm_currency IN ('usd', '$'))

    UNION ALL

    -- Weight Discrepancies (VGM vs PKL)
    SELECT 
        v.shipment_id,
        CAST('{processed_at}' AS TIMESTAMP) AS processed_at,
        'Weight' AS discrepancy_category,
        'Gross Weight (LB)' AS field_flagged,
        CAST(v.gross_weight_lb AS STRING) AS expected_value,
        CAST(p.gross_weight_lb AS STRING) AS actual_value
    FROM LatestVGM v
    JOIN LatestPKLBase p 
        ON v.shipment_id = p.shipment_id
    WHERE v.gross_weight_lb != p.gross_weight_lb

    UNION ALL

    -- Weight Discrepancies (SLI vs PKL KG Weights combined with 1 KG Tolerance)
    SELECT 
        s.shipment_id,
        CAST('{processed_at}' AS TIMESTAMP) AS processed_at,
        'Weight' AS discrepancy_category,
        anomaly.field_flagged,
        anomaly.expected_value,
        anomaly.actual_value
    FROM LatestSLI s
    JOIN LatestPKLBase p 
        ON s.shipment_id = p.shipment_id,
    UNNEST([
        STRUCT(
            'Gross Weight (KG)' AS field_flagged, 
            CAST(p.gross_weight_kg AS STRING) AS expected_value, 
            CAST(ROUND(s.gross_weight_kg, 1) AS STRING) AS actual_value, 
            ABS(p.gross_weight_kg - s.gross_weight_kg) > 1 AS is_error
        ),
        STRUCT(
            'Net Weight (KG)' AS field_flagged, 
            CAST(p.net_weight_kg AS STRING) AS expected_value, 
            CAST(ROUND(s.net_weight_kg, 1) AS STRING) AS actual_value, 
            ABS(p.net_weight_kg - s.net_weight_kg) > 1 AS is_error
        )
    ]) AS anomaly
    WHERE anomaly.is_error = TRUE

    UNION ALL

    -- Material Cross-Validation
    SELECT 
        p.shipment_id,
        CAST('{processed_at}' AS TIMESTAMP) AS processed_at,
        'Material Compliance' AS discrepancy_category,
        'Missing Material Number in CIV' AS field_flagged,
        p.material_number AS expected_value,
        'Missing' AS actual_value
    FROM DistinctPKLMaterials p
    LEFT JOIN DistinctCIVMaterials c 
        ON p.shipment_id = c.shipment_id 
        AND p.material_number = c.material_number
    WHERE c.material_number IS NULL;
    """

    for attempt in range(5):
        try:
            query_job = bq_client.query(audit_query)
            query_job.result()  # Waits for the query job to finish
            print(f"[{shipment_id}] Audit engine complete! Shipment_Anomalies_Tbl has been updated for batch {processed_at}.")
            break
        except Exception as e:
            if ("rateLimitExceeded" in str(e) or "403" in str(e)) and attempt < 4:
                sleep_s = (attempt + 1) * 3
                print(f"[{shipment_id}] Audit query rate limit hit. Retrying in {sleep_s}s (Attempt {attempt + 1}/5)...")
                time.sleep(sleep_s)
            else:
                print(f"[{shipment_id}] CRITICAL ERROR: Failed to run audit query: {e}")
                break


# GCP Cloud Function Entry Point
@functions_framework.cloud_event
def pubsub_trigger(cloud_event):
    try:
        pubsub_message_bytes = base64.b64decode(cloud_event.data["message"]["data"])
        pubsub_message_string = pubsub_message_bytes.decode('utf-8')
        incoming_payload = json.loads(pubsub_message_string)
        
        shipment_id = incoming_payload["shipment_id"]
        document_uris = incoming_payload["files"]
        processed_at = incoming_payload.get("processed_at", datetime.now(ZoneInfo("America/Chicago")).isoformat())
        
        print(f"Received Pub/Sub trigger for Shipment: {shipment_id} (Timestamp: {processed_at})")
    except Exception as e:
        print(f"Error decoding Pub/Sub payload: {e}")
        return
        
    asyncio.run(
        process_shipment_concurrently(
            shipment_id=shipment_id,
            document_uris=document_uris,
            processed_at=processed_at
        )
    )

# === LOCAL TESTING BYPASS ===
if __name__ == "__main__":
    print("Running in local test mode...")
    
    test_shipment_id = "10351463"
    test_processed_at = datetime.now(timezone.utc).isoformat()
    
    # Update these URIs to the exact bucket path you verified earlier!
    test_files = {
        "CIV": "gs://logistic-audit-pdfs/shipment_10351463/CIV_10351463.pdf",
        "PKL": "gs://logistic-audit-pdfs/shipment_10351463/PKL_10351463.pdf",
        "SLI": "gs://logistic-audit-pdfs/shipment_10351463/SLI_10351463.pdf",
        "VGM": "gs://logistic-audit-pdfs/shipment_10351463/VGM_10351463.pdf"
    }
    
    asyncio.run(
        process_shipment_concurrently(
            shipment_id=test_shipment_id,
            document_uris=test_files,
            processed_at=test_processed_at
        )
    )
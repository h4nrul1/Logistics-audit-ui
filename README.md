# 🚢 Logistics Document Auditing System & Master Dashboard (`main` branch)

An automated, end-to-end, AI-powered document processing and cross-validation platform built for logistics and trade compliance teams. 

The platform automatically ingests multi-document shipment packages (Commercial Invoices, Packing Lists, Shipper's Letter of Instructions, Verified Gross Mass) from Google Drive, extracts structured data using **Google Gemini 2.5 Pro** multimodal AI models, executes automated reconciliation rules in **BigQuery**, and provides a **Streamlit Web Dashboard** for human-in-the-loop auditing and anomaly resolution.

---

## 📐 System Architecture Overview

```mermaid
graph TD
    subgraph 1. Ingestion Phase (ingestion/)
        GDrive["Google Drive\n(Target Ingestion Folder)"] -->|Scan & Group PDFs| CRJob["Cloud Run Job\n(shipment-ingestion-job)"]
        CRJob -->|Upload PDFs| GCS["GCS Bucket\n(logistic-audit-pdfs)"]
        CRJob -->|Archive Processed Files| GDriveProc["Google Drive\n(Processed Folder)"]
        CRJob -->|Publish Message| PubSub["Pub/Sub Topic\n(shipment-processing-trigger)"]
    end

    subgraph 2. Multimodal Extraction & Audit Phase (extractions/)
        PubSub -->|Cloud Event| CloudFunc["Extractions Service\n(Cloud Run / Cloud Function)"]
        CloudFunc -->|Async Multimodal Extraction| Gemini["Vertex AI / Gemini 2.5 Pro\n(Structured JSON Schemas)"]
        Gemini -->|Structured JSON| CloudFunc
        CloudFunc -->|Insert Structured Records| BQ_Raw["BigQuery Raw Tables\n(CIV_Tbl, PKL_Tbl, SLI_Tbl, VGM_Tbl)"]
        CloudFunc -->|Execute SQL Reconciliation| BQ_Anom["BigQuery Anomalies Table\n(Shipment_Anomalies_Tbl)"]
    end

    subgraph 3. Human-in-the-Loop Master Dashboard (app.py)
        UI["Streamlit Master Dashboard\n(Cloud Run Service Port 8080/8501)"] <-->|Query Tables| BQ_Raw
        UI <-->|Fetch Discrepancies| BQ_Anom
        UI <-->|Render PDF Documents| GCS
    end
```

---

## 📂 Core Components & Repository Structure

```
logistics-audit-ui/
├── app.py                            # Main Streamlit Master Dashboard application
├── Dockerfile                        # Container definition for Streamlit UI (Port 8501/8080)
├── Procfile                          # Process manager launcher
├── requirements.txt                  # Python dependencies for Streamlit UI
├── reprocess_past_shipments.py       # Batch reprocessing utility for historical shipments
├── ingestion/                        # Google Drive Ingestion Pipeline
│   ├── main.py                       # Drive scanner, file grouper, GCS sync, and Pub/Sub publisher
│   ├── Dockerfile                    # Container definition for Cloud Run Ingestion Job
│   └── requirements.txt              # Ingestion script dependencies
└── extractions/                      # Gemini Multimodal Extraction & Audit Engine
    ├── main.py                       # Event-driven Gemini 2.5 Pro extraction service
    └── requirements.txt              # Extractions service dependencies
```

---

## 🔄 Pipeline Components Breakdown

### 1. Ingestion Pipeline (`ingestion/main.py`)
* **Google Drive Scanning**: Periodically scans Google Drive folder (`1FOnW5J9k763udzfdxW9d8iPg15RQQq2f`) for unprocessed PDF files matching an 8-digit shipment pattern (`_\d{8}`).
* **Document Grouping & Baseline Validation**: Groups files by shipment ID and enforces presence of mandatory document types:
  * **CIV**: Commercial Invoice
  * **PKL**: Packing List
  * **SLI**: Shipper's Letter of Instructions
  * *(Optional: **VGM** - Verified Gross Mass)*
* **Storage Transfer & Event Trigger**:
  * Uploads PDF bytes to GCS bucket `gs://logistic-audit-pdfs/shipment_{shipment_id}/`.
  * Moves processed files in Google Drive to destination folder (`1rAdbu6a9M8mvxdJCSXUduSfQ9RYPuY7u`).
  * Publishes a JSON payload trigger to Pub/Sub topic `shipment-processing-trigger`.

---

### 2. Extractions & SQL Reconciliation Engine (`extractions/main.py`)
* **Multimodal Extraction (Gemini 2.5 Pro)**:
  * Uses Vertex AI `google-genai` SDK (`gemini-2.5-pro`) to process PDF pages asynchronously (`asyncio.gather`) using strict JSON schemas (`temperature=0.0`).
  * **CIV**: Total amount, currency, itemized material numbers, HTS codes, unit prices.
  * **PKL**: Gross/net weights (LB & KG), pallet count, case count, material numbers list.
  * **SLI**: Total USD value, gross/net weights (KG), itemized package line items.
  * **VGM**: Certified gross weight (LB & KG).
* **BigQuery Ingestion**:
  * Writes extracted JSON directly into BigQuery dataset `it-ai-briggs-agentspace.logistics_dataset`: `CIV_Tbl`, `PKL_Tbl`, `SLI_Tbl`, and `VGM_Tbl`.
* **Automated SQL Cross-Validation Query**:
  * Evaluates financial discrepancies (`CIV total_amount` vs `SLI total_value_usd`).
  * Evaluates weight discrepancies (`SLI gross/net KG` vs `PKL gross/net KG` with a 1.0 KG tolerance buffer, and `VGM certified weight` vs `PKL gross weight`).
  * Checks material compliance (`PKL material numbers` vs `CIV material numbers`).
  * Populates `Shipment_Anomalies_Tbl` with flagged discrepancies.

---

### 3. Master Streamlit Dashboard (`app.py`)
A web interface built with Streamlit providing logistics auditors with a control tower:
* **Master Audit Queue**: Real-time status list (`Passed`, `Failed`, `Resolved`) with status filters and shipment search.
* **Sync New Documents**: Programmatically triggers Cloud Run Job `shipment-ingestion-job` via `google.cloud.run_v2.JobsClient` and polls BigQuery for updates.
* **Inspection Workspace**: Embedded Base64 PDF viewer inside iframe with document switcher (`CIV`, `PKL`, `SLI`, `VGM`), discrepancy breakdown, and resolution controls.

---

### 4. Admin Reprocessing Utility (`reprocess_past_shipments.py`)
* Discovers all historical shipment folders in GCS bucket `logistic-audit-pdfs`.
* Preserves original BigQuery document timestamps, truncates destination BigQuery tables, and re-publishes Pub/Sub extraction triggers to re-run extraction and audit rules across historical data.

---

## ☁️ Google Cloud Infrastructure Reference

| Component | Resource ID / Name | Description |
| :--- | :--- | :--- |
| **GCP Project** | `it-ai-briggs-agentspace` | Target Google Cloud project. |
| **GCP Region** | `us-central1` | Deployment region. |
| **GCS Bucket** | `logistic-audit-pdfs` | Document storage (`shipment_{id}/`). |
| **Pub/Sub Topic** | `shipment-processing-trigger` | Asynchronous trigger topic. |
| **Cloud Run Job** | `shipment-ingestion-job` | Ingestion container job. |
| **BigQuery Dataset** | `logistics_dataset` | Data warehouse containing `CIV_Tbl`, `PKL_Tbl`, `SLI_Tbl`, `VGM_Tbl`, and `Shipment_Anomalies_Tbl`. |

---

## 🚀 Local Setup & Execution Guide

### Prerequisites
- Python 3.10+
- Google Cloud SDK (`gcloud`) authenticated with access to `it-ai-briggs-agentspace`

### Running Streamlit Dashboard Locally
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Authenticate GCP credentials
gcloud auth application-default login

# 3. Launch Streamlit UI
streamlit run app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser.

---

### Running Ingestion Locally
```bash
cd ingestion
pip install -r requirements.txt
python main.py
```

---

### Running Reprocessing Script
```bash
python reprocess_past_shipments.py
```

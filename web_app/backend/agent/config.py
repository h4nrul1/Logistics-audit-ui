import os

PROJECT_ID = os.getenv("GCP_PROJECT", "it-ai-briggs-agentspace")
DATASET_ID = "logistics_dataset"
BUCKET_NAME = "logistic-audit-pdfs"
LOCATION = "us-central1"

DEFAULT_MODEL = "gemini-2.5-pro"

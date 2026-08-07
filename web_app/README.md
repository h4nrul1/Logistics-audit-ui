# 🚀 Logistics Audit AI Web Application (v2.0)

A high-performance Web Application featuring a client-side **React + Vite** frontend and a **Python FastAPI** backend for instant 0ms document inspection, live cross-validation, and ReportLab PDF re-generation.

---

## 📁 Directory Structure

```
logistics-audit-ui/
└── web_app/
    ├── backend/
    │   ├── server.py             # FastAPI REST API & Static File Server
    │   └── requirements.txt      # Python dependencies (fastapi, uvicorn, etc.)
    └── frontend/
        ├── index.html            # Main HTML entry with SEO metadata
        ├── src/
        │   ├── index.css         # Glassmorphism theme tokens & animations
        │   ├── App.jsx           # Main React component
        │   ├── components/       # Header, QueueTable, InspectionView, PdfViewer, etc.
        │   └── services/api.js   # Async REST API service client
        └── dist/                 # Compiled static production build
```

---

## 🏃 Running Locally

### Option 1: Single Command (FastAPI serves built React frontend)
1. Run the FastAPI server:
   ```bash
   py -3 web_app/backend/server.py
   ```
2. Open **`http://localhost:8000`** in your browser!

### Option 2: Live React Dev Server with Hot Reloading
1. Start the FastAPI backend on port 8000:
   ```bash
   py -3 web_app/backend/server.py
   ```
2. In a separate terminal, start Vite dev server:
   ```bash
   cd web_app/frontend
   cmd /c "npm run dev"
   ```
3. Open **`http://localhost:5173`** in your browser!

---

## ☁️ Deployment to Cloud Run

To deploy the new Web Application to Google Cloud Run:
```bash
gcloud run deploy logistics-uat-dashboard \
  --source=./web_app/backend \
  --region=us-central1 \
  --project=it-ai-briggs-agentspace \
  --allow-unauthenticated
```

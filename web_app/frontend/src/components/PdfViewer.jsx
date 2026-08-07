import React, { useState } from "react";
import { FileText, Sparkles, AlertCircle } from "lucide-react";
import { getPdfStreamUrl } from "../services/api";

export default function PdfViewer({ shipmentId, pdfFiles }) {
  // Determine available document types
  const docMap = {};
  pdfFiles.forEach(f => {
    const name = f.name.toLowerCase();
    let docType = "OTHER";
    if (name.includes("civ")) docType = "CIV";
    else if (name.includes("pkl")) docType = "PKL";
    else if (name.includes("sli")) docType = "SLI";
    else if (name.includes("vgm")) docType = "VGM";

    if (!docMap[docType]) {
      docMap[docType] = { original: null, audited: null };
    }
    if (f.is_audited) {
      docMap[docType].audited = f;
    } else {
      docMap[docType].original = f;
    }
  });

  const availableTypes = Object.keys(docMap).sort((a, b) => {
    const order = { CIV: 1, PKL: 2, SLI: 3, VGM: 4 };
    return (order[a] || 5) - (order[b] || 5);
  });

  const [selectedType, setSelectedType] = useState(availableTypes[0] || "CIV");
  const [version, setVersion] = useState("original"); // 'original' or 'audited'

  if (availableTypes.length === 0) {
    return (
      <div className="glass-card" style={{ padding: "24px", textAlign: "center" }}>
        <AlertCircle size={32} color="var(--text-muted)" style={{ margin: "0 auto 12px" }} />
        <p style={{ color: "var(--text-muted)" }}>No PDF documents found in GCS for this shipment.</p>
      </div>
    );
  }

  const currentDocs = docMap[selectedType] || { original: null, audited: null };
  const hasAudited = !!currentDocs.audited;

  // Auto-switch to Audited PDF when available
  React.useEffect(() => {
    if (hasAudited) {
      setVersion("audited");
    } else {
      setVersion("original");
    }
  }, [selectedType, hasAudited]);

  const activeFile = (version === "audited" && hasAudited) ? currentDocs.audited : currentDocs.original;

  return (
    <div className="glass-card" style={{ padding: "20px" }}>
      <h3 style={{ fontSize: "1.1rem", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
        <FileText size={18} color="var(--accent-primary)" />
        <span>📄 Document Viewer</span>
      </h3>

      {/* Document Type Tabs */}
      <div style={{ display: "flex", gap: "8px", marginBottom: "16px", borderBottom: "1px solid var(--bg-card-border)", paddingBottom: "12px", overflowX: "auto" }}>
        {availableTypes.map(type => (
          <button
            key={type}
            onClick={() => {
              setSelectedType(type);
              if (!docMap[type].audited && version === "audited") {
                setVersion("original");
              }
            }}
            style={{
              padding: "6px 14px",
              borderRadius: "8px",
              fontWeight: "600",
              fontSize: "0.85rem",
              cursor: "pointer",
              border: "1px solid var(--bg-card-border)",
              background: selectedType === type ? "var(--accent-glow)" : "transparent",
              color: selectedType === type ? "var(--accent-primary)" : "var(--text-muted)",
              transition: "var(--transition-fast)"
            }}
          >
            {type}
          </button>
        ))}
      </div>

      {/* Version Toggle (Original vs Audited) */}
      <div style={{ marginBottom: "16px", display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(0, 0, 0, 0.15)", padding: "8px 12px", borderRadius: "8px" }}>
        <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
          {hasAudited ? (
            <span style={{ color: "var(--status-passed)", display: "inline-flex", alignItems: "center", gap: "4px" }}>
              <Sparkles size={14} /> Audited PDF Available
            </span>
          ) : (
            "Viewing Original PDF"
          )}
        </span>

        {hasAudited && (
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              onClick={() => setVersion("original")}
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "0.78rem",
                fontWeight: "600",
                cursor: "pointer",
                border: "1px solid var(--bg-card-border)",
                background: version === "original" ? "rgba(255, 255, 255, 0.15)" : "transparent",
                color: version === "original" ? "var(--text-main)" : "var(--text-muted)"
              }}
            >
              Original PDF
            </button>
            <button
              onClick={() => setVersion("audited")}
              style={{
                padding: "4px 10px",
                borderRadius: "6px",
                fontSize: "0.78rem",
                fontWeight: "600",
                cursor: "pointer",
                border: "1px solid var(--status-passed)",
                background: version === "audited" ? "var(--status-passed-bg)" : "transparent",
                color: version === "audited" ? "var(--status-passed)" : "var(--text-muted)"
              }}
            >
              Audited PDF
            </button>
          </div>
        )}
      </div>

      {/* PDF Stream Frame (Instant Client Rendering) */}
      {activeFile ? (
        <iframe
          key={activeFile.blob_name}
          src={getPdfStreamUrl(shipmentId, activeFile.blob_name)}
          style={{ width: "100%", height: "650px", border: "none", borderRadius: "8px", background: "#ffffff" }}
          title={activeFile.name}
        />
      ) : (
        <div style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)" }}>
          No file selected for {selectedType}.
        </div>
      )}
    </div>
  );
}

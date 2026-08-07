import React, { useState, useEffect } from "react";
import { Edit3, Save, CheckCircle, Loader2, RotateCcw } from "lucide-react";

export default function CorrectionsForm({ documents, pdfFiles, onSave, onReset, isSaving, resettingDoc }) {
  const [formState, setFormState] = useState({});
  const [openExpanders, setOpenExpanders] = useState({ CIV: true, PKL: true, SLI: true, VGM: true });

  // Calculate which document types have audited PDFs
  const auditedDocs = [];
  (pdfFiles || []).forEach(f => {
    if (f.is_audited || f.name.toLowerCase().includes("_audited")) {
      const filename = (f.name || f.blob_name || "").split('/').pop().toLowerCase();
      let dt = "OTHER";
      if (filename.startsWith("civ") || filename.includes("civ")) dt = "CIV";
      else if (filename.startsWith("pkl") || filename.includes("pkl")) dt = "PKL";
      else if (filename.startsWith("sli") || filename.includes("sli")) dt = "SLI";
      else if (filename.startsWith("vgm") || filename.includes("vgm")) dt = "VGM";

      if (dt !== "OTHER" && !auditedDocs.includes(dt)) {
        auditedDocs.push(dt);
      }
    }
  });
  auditedDocs.sort((a, b) => {
    const order = { CIV: 1, PKL: 2, SLI: 3, VGM: 4 };
    return (order[a] || 5) - (order[b] || 5);
  });

  // Initialize form state from documents prop
  useEffect(() => {
    const initialState = {};
    ["CIV", "PKL", "SLI", "VGM"].forEach(dt => {
      if (documents[dt]) {
        initialState[dt] = { ...documents[dt] };
      }
    });
    setFormState(initialState);
  }, [documents]);

  const handleScalarChange = (dt, field, value) => {
    setFormState(prev => ({
      ...prev,
      [dt]: {
        ...prev[dt],
        [field]: value
      }
    }));
  };

  const handleItemChange = (dt, idx, field, value) => {
    setFormState(prev => {
      const items = [...(prev[dt]?.items || [])];
      items[idx] = { ...items[idx], [field]: value };
      return {
        ...prev,
        [dt]: {
          ...prev[dt],
          items
        }
      };
    });
  };

  const toggleExpander = (dt) => {
    setOpenExpanders(prev => ({ ...prev, [dt]: !prev[dt] }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    onSave(formState);
  };

  return (
    <div className="glass-card" style={{ padding: "20px" }}>
      <h3 style={{ fontSize: "1.1rem", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
        <Edit3 size={18} color="var(--accent-primary)" />
        <span>✍️ Auditor Overrides & Correction Entry</span>
      </h3>

      <form onSubmit={handleSubmit}>
        {/* CIV Section */}
        {documents.CIV && (
          <div style={{ marginBottom: "12px", border: "1px solid var(--bg-card-border)", borderRadius: "8px", overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => toggleExpander("CIV")}
              style={{ width: "100%", padding: "10px 14px", background: "rgba(0,0,0,0.2)", border: "none", color: "var(--text-main)", fontWeight: "600", fontSize: "0.9rem", textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
            >
              <span>📝 CIV Corrections</span>
              <span>{openExpanders.CIV ? "▲" : "▼"}</span>
            </button>
            {openExpanders.CIV && (
              <div style={{ padding: "14px" }}>
                <label style={{ display: "block", fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "4px" }}>Total Amount (USD):</label>
                <input
                  type="number"
                  step="0.01"
                  value={formState.CIV?.total_amount ?? ""}
                  onChange={e => handleScalarChange("CIV", "total_amount", parseFloat(e.target.value) || 0)}
                  style={{ width: "100%" }}
                />
              </div>
            )}
          </div>
        )}

        {/* PKL Section */}
        {documents.PKL && (
          <div style={{ marginBottom: "12px", border: "1px solid var(--bg-card-border)", borderRadius: "8px", overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => toggleExpander("PKL")}
              style={{ width: "100%", padding: "10px 14px", background: "rgba(0,0,0,0.2)", border: "none", color: "var(--text-main)", fontWeight: "600", fontSize: "0.9rem", textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
            >
              <span>📝 PKL Corrections</span>
              <span>{openExpanders.PKL ? "▲" : "▼"}</span>
            </button>
            {openExpanders.PKL && (
              <div style={{ padding: "14px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Gross Wt (lb):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.PKL?.gross_weight_lb ?? ""}
                    onChange={e => handleScalarChange("PKL", "gross_weight_lb", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Gross Wt (kg):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.PKL?.gross_weight_kg ?? ""}
                    onChange={e => handleScalarChange("PKL", "gross_weight_kg", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Net Wt (lb):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.PKL?.net_weight_lb ?? ""}
                    onChange={e => handleScalarChange("PKL", "net_weight_lb", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Net Wt (kg):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.PKL?.net_weight_kg ?? ""}
                    onChange={e => handleScalarChange("PKL", "net_weight_kg", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Pallet Count:</label>
                  <input
                    type="number"
                    step="1"
                    value={formState.PKL?.pallet_count ?? ""}
                    onChange={e => handleScalarChange("PKL", "pallet_count", parseInt(e.target.value, 10) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Loose Case Count:</label>
                  <input
                    type="number"
                    step="1"
                    value={formState.PKL?.loose_case_count ?? ""}
                    onChange={e => handleScalarChange("PKL", "loose_case_count", parseInt(e.target.value, 10) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* SLI Section */}
        {documents.SLI && (
          <div style={{ marginBottom: "12px", border: "1px solid var(--bg-card-border)", borderRadius: "8px", overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => toggleExpander("SLI")}
              style={{ width: "100%", padding: "10px 14px", background: "rgba(0,0,0,0.2)", border: "none", color: "var(--text-main)", fontWeight: "600", fontSize: "0.9rem", textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
            >
              <span>📝 SLI Corrections</span>
              <span>{openExpanders.SLI ? "▲" : "▼"}</span>
            </button>
            {openExpanders.SLI && (
              <div style={{ padding: "14px" }}>
                <div style={{ marginBottom: "12px" }}>
                  <label style={{ display: "block", fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "4px" }}>Total Value (USD):</label>
                  <input
                    type="number"
                    step="0.01"
                    value={formState.SLI?.total_value_usd ?? ""}
                    onChange={e => handleScalarChange("SLI", "total_value_usd", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>

                {/* SLI Package Items */}
                {(formState.SLI?.items || []).map((item, idx) => (
                  <div key={idx} style={{ background: "rgba(0,0,0,0.15)", padding: "10px", borderRadius: "6px", marginBottom: "8px" }}>
                    <span style={{ fontSize: "0.8rem", fontWeight: "600", color: "var(--accent-primary)", display: "block", marginBottom: "6px" }}>📦 Item #{idx + 1}</span>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "8px" }}>
                      <div>
                        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Value (USD)</label>
                        <input
                          type="number"
                          step="0.01"
                          value={item.value_usd ?? ""}
                          onChange={e => handleItemChange("SLI", idx, "value_usd", parseFloat(e.target.value) || 0)}
                          style={{ width: "100%" }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Gross Wt (kg)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={item.gross_weight_kg ?? ""}
                          onChange={e => handleItemChange("SLI", idx, "gross_weight_kg", parseFloat(e.target.value) || 0)}
                          style={{ width: "100%" }}
                        />
                      </div>
                      <div>
                        <label style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Net Wt (kg)</label>
                        <input
                          type="number"
                          step="0.1"
                          value={item.net_weight_kg ?? ""}
                          onChange={e => handleItemChange("SLI", idx, "net_weight_kg", parseFloat(e.target.value) || 0)}
                          style={{ width: "100%" }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* VGM Section */}
        {documents.VGM && (
          <div style={{ marginBottom: "12px", border: "1px solid var(--bg-card-border)", borderRadius: "8px", overflow: "hidden" }}>
            <button
              type="button"
              onClick={() => toggleExpander("VGM")}
              style={{ width: "100%", padding: "10px 14px", background: "rgba(0,0,0,0.2)", border: "none", color: "var(--text-main)", fontWeight: "600", fontSize: "0.9rem", textAlign: "left", cursor: "pointer", display: "flex", justifyContent: "space-between" }}
            >
              <span>📝 VGM Corrections</span>
              <span>{openExpanders.VGM ? "▲" : "▼"}</span>
            </button>
            {openExpanders.VGM && (
              <div style={{ padding: "14px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Gross Wt (lb):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.VGM?.gross_weight_lb ?? ""}
                    onChange={e => handleScalarChange("VGM", "gross_weight_lb", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: "2px" }}>Gross Wt (kg):</label>
                  <input
                    type="number"
                    step="0.1"
                    value={formState.VGM?.gross_weight_kg ?? ""}
                    onChange={e => handleScalarChange("VGM", "gross_weight_kg", parseFloat(e.target.value) || 0)}
                    style={{ width: "100%" }}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Submit Button */}
        <button
          type="submit"
          className="btn btn-primary"
          disabled={isSaving}
          style={{ width: "100%", padding: "12px", marginTop: "12px", opacity: isSaving ? 0.7 : 1, cursor: isSaving ? "not-allowed" : "pointer" }}
        >
          {isSaving ? (
            <>
              <Loader2 size={18} className="spin-icon" />
              <span>Saving Overrides & Re-generating PDFs...</span>
            </>
          ) : (
            <>
              <Save size={18} />
              <span>💾 Save All Corrections & Re-generate PDFs</span>
            </>
          )}
        </button>

        {/* Reset Corrections Section (Dedicated Reset button for each document type that was audited) */}
        {auditedDocs.length > 0 && (
          <div style={{ marginTop: "24px", paddingTop: "16px", borderTop: "1px solid var(--bg-card-border)" }}>
            <h4 style={{ fontSize: "0.95rem", fontWeight: "600", marginBottom: "12px", display: "flex", alignItems: "center", gap: "6px", color: "var(--text-muted)" }}>
              <RotateCcw size={16} /> 🗑️ Reset Audit Corrections
            </h4>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(auditedDocs.length, 4)}, 1fr)`, gap: "8px" }}>
              {auditedDocs.map(dt => (
                <button
                  key={dt}
                  type="button"
                  onClick={() => onReset(dt)}
                  disabled={resettingDoc === dt}
                  style={{
                    padding: "8px 12px",
                    borderRadius: "8px",
                    border: "1px solid var(--status-failed)",
                    background: resettingDoc === dt ? "rgba(239, 68, 68, 0.15)" : "transparent",
                    color: "var(--status-failed)",
                    fontWeight: "600",
                    fontSize: "0.82rem",
                    cursor: resettingDoc === dt ? "not-allowed" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "6px",
                    transition: "var(--transition-fast)"
                  }}
                >
                  {resettingDoc === dt ? (
                    <>
                      <Loader2 size={14} className="spin-icon" />
                      <span>Resetting...</span>
                    </>
                  ) : (
                    <>
                      <RotateCcw size={14} />
                      <span>Reset {dt}</span>
                    </>
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </form>
    </div>
  );
}

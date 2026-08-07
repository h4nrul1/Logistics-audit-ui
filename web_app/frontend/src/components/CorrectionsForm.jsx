import React, { useState, useEffect } from "react";
import { Edit3, Save, CheckCircle, Loader2 } from "lucide-react";

export default function CorrectionsForm({ documents, onSave, isSaving }) {
  const [formState, setFormState] = useState({});
  const [openExpanders, setOpenExpanders] = useState({ CIV: true, PKL: true, SLI: true, VGM: true });

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
      <h3 style={{ fontSize: "1.1rem", marginBottom: "8px", display: "flex", alignItems: "center", gap: "8px" }}>
        <Edit3 size={18} color="var(--accent-primary)" />
        <span>✏️ Auditor Corrections & Re-generation</span>
      </h3>
      <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "16px" }}>
        Type overrides below. All changes persist instantly across document view switches.
      </p>

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
                <label style={{ display: "block", fontSize: "0.82rem", color: "var(--text-muted)", marginBottom: "4px" }}>Total Invoice Amount (USD):</label>
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
      </form>
    </div>
  );
}

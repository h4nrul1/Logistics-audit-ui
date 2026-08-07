import React from "react";
import { AlertTriangle, CheckCircle2, DollarSign, Globe, Tag } from "lucide-react";

export default function AnomaliesPanel({ anomalies, indicators, foreignCurrency }) {
  const zeroCount = indicators?.zero_count || 0;
  const htsGroups = indicators?.hts_groups || {};

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", marginBottom: "20px" }}>
      {/* Foreign Currency Banner */}
      {foreignCurrency && (
        <div style={{ background: "rgba(56, 189, 248, 0.12)", border: "1px solid rgba(56, 189, 248, 0.3)", borderRadius: "var(--border-radius)", padding: "12px 16px", display: "flex", alignItems: "center", gap: "12px" }}>
          <Globe size={20} color="var(--accent-primary)" />
          <span style={{ fontSize: "0.88rem", fontWeight: "500", color: "var(--accent-primary)" }}>
            <strong>💱 Foreign Currency Detected ({foreignCurrency})</strong>: Financial total cross-validation audit is automatically bypassed for this shipment.
          </span>
        </div>
      )}

      {/* $0 Items Warning Callout & HTS Breakdown */}
      {zeroCount > 0 && (
        <div className="glass-card" style={{ padding: "16px", borderColor: "rgba(245, 158, 11, 0.4)", background: "var(--status-resolved-bg)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "12px" }}>
            <Tag size={18} color="var(--status-resolved)" />
            <h4 style={{ fontSize: "0.95rem", color: "var(--status-resolved)" }}>
              🏷️ $0 Priced Items Detected: Found {zeroCount} item(s) valued at $0.00 across {Object.keys(htsGroups).length} HTS code(s).
            </h4>
          </div>

          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.1)", color: "var(--text-muted)" }}>
                <th style={{ padding: "6px 8px" }}>HTS Code</th>
                <th style={{ padding: "6px 8px", textAlign: "left" }}>$0 Item Count</th>
                <th style={{ padding: "6px 8px" }}>Material / Part Numbers</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(htsGroups).map(([hts, info]) => (
                <tr key={hts} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.05)" }}>
                  <td style={{ padding: "6px 8px", fontWeight: "600" }}>{hts}</td>
                  <td style={{ padding: "6px 8px", textAlign: "left", fontWeight: "600" }}>{info.count}</td>
                  <td style={{ padding: "6px 8px", color: "var(--text-muted)" }}>
                    {info.materials?.length ? info.materials.join(", ") : "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Anomalies Table */}
      <div className="glass-card" style={{ padding: "20px" }}>
        <h3 style={{ fontSize: "1.1rem", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
          <AlertTriangle size={18} color="var(--status-failed)" />
          <span>⚠️ Identified Anomalies</span>
        </h3>

        {anomalies.length === 0 ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--status-passed)", background: "var(--status-passed-bg)", borderRadius: "8px", fontWeight: "600" }}>
            🎉 No anomalies found! This shipment passed all automated checks.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--bg-card-border)", color: "var(--text-muted)", textTransform: "uppercase" }}>
                  <th style={{ padding: "10px 12px" }}>Category</th>
                  <th style={{ padding: "10px 12px" }}>Flagged Field</th>
                  <th style={{ padding: "10px 12px" }}>Expected Value</th>
                  <th style={{ padding: "10px 12px" }}>Actual Value</th>
                </tr>
              </thead>
              <tbody>
                {anomalies.map((anom, idx) => (
                  <tr key={idx} style={{ borderBottom: "1px solid var(--bg-card-border)" }}>
                    <td style={{ padding: "10px 12px", fontWeight: "600" }}>{anom.discrepancy_category}</td>
                    <td style={{ padding: "10px 12px", color: "var(--accent-primary)" }}>{anom.field_flagged}</td>
                    <td style={{ padding: "10px 12px", fontWeight: "600", color: "var(--status-passed)" }}>{anom.expected_value}</td>
                    <td style={{ padding: "10px 12px", fontWeight: "600", color: "var(--status-failed)" }}>{anom.actual_value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

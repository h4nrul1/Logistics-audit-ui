import React, { useState, useMemo } from "react";
import { Search, Filter, ArrowUpDown, ChevronRight, CheckCircle2, AlertTriangle, CheckCheck } from "lucide-react";

export default function QueueTable({ shipments, onSelectShipment }) {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedStatuses, setSelectedStatuses] = useState(["Passed", "Failed", "Resolved"]);
  const [selectedCategories, setSelectedCategories] = useState(["Financial", "Weight", "Material Compliance", "None"]);
  const [sortOrder, setSortOrder] = useState("desc"); // 'asc', 'desc', 'default'

  // Multiselect Toggle Helpers
  const toggleStatus = (st) => {
    setSelectedStatuses(prev => 
      prev.includes(st) ? prev.filter(s => s !== st) : [...prev, st]
    );
  };

  const toggleCategory = (cat) => {
    setSelectedCategories(prev => 
      prev.includes(cat) ? prev.filter(c => c !== cat) : [...prev, cat]
    );
  };

  const toggleSort = () => {
    if (sortOrder === "desc") setSortOrder("asc");
    else if (sortOrder === "asc") setSortOrder("default");
    else setSortOrder("desc");
  };

  // Filter & Sort Logic (Instant Client-Side State)
  const filteredShipments = useMemo(() => {
    return shipments.filter(s => {
      // 1. Search term match
      if (searchTerm.trim() && !s.shipment_id.toLowerCase().includes(searchTerm.toLowerCase().trim())) {
        return false;
      }
      // 2. Status match
      if (!selectedStatuses.includes(s.status)) {
        return false;
      }
      // 3. Category match
      if (s.categories === "None") {
        if (!selectedCategories.includes("None")) return false;
      } else {
        const cats = s.categories.split(",").map(c => c.strip ? c.strip() : c.trim());
        const matches = cats.some(c => selectedCategories.includes(c));
        if (!matches) return false;
      }
      return true;
    }).sort((a, b) => {
      if (sortOrder === "default") return 0;
      const tA = new Date(a.processed_at || 0).getTime();
      const tB = new Date(b.processed_at || 0).getTime();
      return sortOrder === "asc" ? tA - tB : tB - tA;
    });
  }, [shipments, searchTerm, selectedStatuses, selectedCategories, sortOrder]);

  return (
    <div className="glass-card" style={{ padding: "24px" }}>
      <div style={{ marginBottom: "20px" }}>
        <h2 style={{ fontSize: "1.25rem", marginBottom: "16px", display: "flex", alignItems: "center", gap: "8px" }}>
          <span>📋 Master Audit Queue</span>
          <span style={{ fontSize: "0.85rem", fontWeight: "500", color: "var(--text-muted)", background: "rgba(255, 255, 255, 0.08)", padding: "2px 8px", borderRadius: "12px" }}>
            {filteredShipments.length} Shipment{filteredShipments.length === 1 ? "" : "s"}
          </span>
        </h2>

        {/* Filter Controls Row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "16px", alignItems: "center" }}>
          {/* Search Bar */}
          <div style={{ position: "relative" }}>
            <Search size={16} style={{ position: "absolute", left: "12px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }} />
            <input 
              type="text" 
              placeholder="Search Shipment ID..." 
              value={searchTerm} 
              onChange={e => setSearchTerm(e.target.value)}
              style={{ width: "100%", paddingLeft: "36px" }}
            />
          </div>

          {/* Status Filters */}
          <div>
            <span style={{ fontSize: "0.78rem", fontWeight: "600", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Filter Status:</span>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {["Passed", "Failed", "Resolved"].map(st => {
                const active = selectedStatuses.includes(st);
                return (
                  <button 
                    key={st}
                    onClick={() => toggleStatus(st)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: "6px",
                      fontSize: "0.8rem",
                      fontWeight: "600",
                      cursor: "pointer",
                      border: "1px solid var(--bg-card-border)",
                      background: active ? `var(--status-${st.toLowerCase()}-bg)` : "transparent",
                      color: active ? `var(--status-${st.toLowerCase()})` : "var(--text-muted)",
                      opacity: active ? 1 : 0.6
                    }}
                  >
                    {st}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Category Filters */}
          <div>
            <span style={{ fontSize: "0.78rem", fontWeight: "600", color: "var(--text-muted)", display: "block", marginBottom: "4px" }}>Filter Category:</span>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {["Financial", "Weight", "Material Compliance", "None"].map(cat => {
                const active = selectedCategories.includes(cat);
                return (
                  <button 
                    key={cat}
                    onClick={() => toggleCategory(cat)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: "6px",
                      fontSize: "0.78rem",
                      fontWeight: "500",
                      cursor: "pointer",
                      border: "1px solid var(--bg-card-border)",
                      background: active ? "var(--accent-glow)" : "transparent",
                      color: active ? "var(--accent-primary)" : "var(--text-muted)",
                      opacity: active ? 1 : 0.6
                    }}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Sort Button */}
          <div style={{ justifySelf: "end" }}>
            <button className="btn btn-secondary" onClick={toggleSort} style={{ padding: "8px 12px", fontSize: "0.82rem" }}>
              <ArrowUpDown size={14} />
              Processed At {sortOrder === "asc" ? "🔼 (Asc)" : sortOrder === "desc" ? "🔽 (Desc)" : "↕️ (Default)"}
            </button>
          </div>
        </div>
      </div>

      {/* Queue Table */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.9rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--bg-card-border)", color: "var(--text-muted)", fontSize: "0.8rem", textTransform: "uppercase" }}>
              <th style={{ padding: "12px 16px" }}>Shipment ID</th>
              <th style={{ padding: "12px 16px" }}>Status</th>
              <th style={{ padding: "12px 16px" }}>Categories</th>
              <th style={{ padding: "12px 16px" }}>Indicators</th>
              <th style={{ padding: "12px 16px" }}>Processed At (CT)</th>
              <th style={{ padding: "12px 16px", textAlign: "right" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {filteredShipments.length === 0 ? (
              <tr>
                <td colSpan="6" style={{ padding: "32px", textAlign: "center", color: "var(--text-muted)" }}>
                  No shipments found matching current filters.
                </td>
              </tr>
            ) : (
              filteredShipments.map(s => {
                const statusClass = s.status.toLowerCase();
                return (
                  <tr 
                    key={s.shipment_id}
                    onClick={() => onSelectShipment(s.shipment_id)}
                    style={{ 
                      borderBottom: "1px solid var(--bg-card-border)", 
                      cursor: "pointer", 
                      transition: "var(--transition-fast)" 
                    }}
                    className="queue-row"
                  >
                    <td style={{ padding: "14px 16px", fontWeight: "700", fontFamily: "var(--font-heading)" }}>
                      {s.shipment_id}
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      <span className={`status-pill ${statusClass}`}>
                        {s.status === "Passed" && <CheckCircle2 size={14} />}
                        {s.status === "Failed" && <AlertTriangle size={14} />}
                        {s.status === "Resolved" && <CheckCheck size={14} />}
                        {s.status}
                      </span>
                    </td>
                    <td style={{ padding: "14px 16px", color: "var(--text-muted)" }}>
                      {s.categories}
                    </td>
                    <td style={{ padding: "14px 16px" }}>
                      {s.indicators === "None" ? (
                        <span style={{ color: "var(--text-dim)" }}>None</span>
                      ) : (
                        <span className="badge-chip" style={{ color: "var(--accent-primary)", borderColor: "var(--accent-glow)" }}>
                          {s.indicators}
                        </span>
                      )}
                    </td>
                    <td style={{ padding: "14px 16px", color: "var(--text-muted)", fontSize: "0.85rem" }}>
                      {s.processed_at ? new Date(s.processed_at).toLocaleString("en-US", { timeZone: "America/Chicago" }) : "N/A"}
                    </td>
                    <td style={{ padding: "14px 16px", textAlign: "right" }}>
                      <button className="btn btn-secondary" style={{ padding: "4px 10px", fontSize: "0.8rem" }}>
                        Inspect <ChevronRight size={14} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

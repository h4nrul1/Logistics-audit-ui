import React, { useState, useEffect } from "react";
import Header from "./components/Header";
import QueueTable from "./components/QueueTable";
import InspectionView from "./components/InspectionView";
import AgentCanvasView from "./components/AgentCanvasView";
import { fetchQueue, triggerSync, fetchShipmentDetail } from "./services/api";

export default function App() {
  const [viewMode, setViewMode] = useState("canvas"); // 'canvas' or 'grid'
  const [view, setView] = useState("master"); // 'master' or 'detail' (for grid mode)
  const [selectedShipment, setSelectedShipment] = useState(null); // Defaults to null (no document shown until requested)
  const [shipmentDetail, setShipmentDetail] = useState(null);
  const [shipments, setShipments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [theme, setTheme] = useState("dark");

  const loadQueue = async () => {
    try {
      setLoading(true);
      const data = await fetchQueue();
      const list = data.shipments || [];
      setShipments(list);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  // Fetch detail for selectedShipment when selected
  useEffect(() => {
    if (selectedShipment) {
      fetchShipmentDetail(selectedShipment)
        .then((data) => setShipmentDetail(data))
        .catch((err) => console.error("Error loading shipment detail:", err));
    } else {
      setShipmentDetail(null);
    }
  }, [selectedShipment]);

  const handleSync = async () => {
    try {
      setIsSyncing(true);
      await triggerSync();
      await loadQueue();
      if (selectedShipment) {
        const data = await fetchShipmentDetail(selectedShipment);
        setShipmentDetail(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setIsSyncing(false);
    }
  };

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    document.documentElement.setAttribute("data-theme", nextTheme);
  };

  // Stats calculation
  const stats = {
    total: shipments.length,
    passed: shipments.filter(s => s.status === "Passed").length,
    failed: shipments.filter(s => s.status === "Failed").length,
    resolved: shipments.filter(s => s.status === "Resolved").length,
  };

  const handleViewModeChange = (mode) => {
    setViewMode(mode);
    if (mode === "canvas") {
      setSelectedShipment(null);
    }
  };

  return (
    <div style={{ padding: "20px 24px", maxWidth: "1750px", margin: "0 auto" }}>
      <Header
        stats={stats}
        onSync={handleSync}
        isSyncing={isSyncing}
        theme={theme}
        onToggleTheme={toggleTheme}
        viewMode={viewMode}
        onViewModeChange={handleViewModeChange}
      />

      <main>
        <div style={{ display: viewMode === "canvas" ? "block" : "none" }}>
          <AgentCanvasView
            selectedShipment={selectedShipment}
            shipmentDetail={shipmentDetail}
            onSelectShipment={setSelectedShipment}
            onRefresh={loadQueue}
          />
        </div>

        {viewMode === "grid" && (
          view === "master" ? (
            loading ? (
              <div className="glass-card" style={{ padding: "48px", textAlign: "center" }}>
                <p style={{ color: "var(--text-muted)" }}>Loading Master Audit Queue...</p>
              </div>
            ) : (
              <QueueTable
                shipments={shipments}
                onSelectShipment={(id) => {
                  setSelectedShipment(id);
                  setView("detail");
                }}
              />
            )
          ) : (
            <InspectionView
              shipmentId={selectedShipment}
              onBack={() => {
                setView("master");
                loadQueue();
              }}
            />
          )
        )}
      </main>
    </div>
  );
}

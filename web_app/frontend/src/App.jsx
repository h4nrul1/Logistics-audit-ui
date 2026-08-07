import React, { useState, useEffect } from "react";
import Header from "./components/Header";
import QueueTable from "./components/QueueTable";
import InspectionView from "./components/InspectionView";
import { fetchQueue, triggerSync } from "./services/api";

export default function App() {
  const [view, setView] = useState("master"); // 'master' or 'detail'
  const [selectedShipment, setSelectedShipment] = useState(null);
  const [shipments, setShipments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [theme, setTheme] = useState("dark");

  const loadQueue = async () => {
    try {
      setLoading(true);
      const data = await fetchQueue();
      setShipments(data.shipments || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadQueue();
  }, []);

  const handleSync = async () => {
    try {
      setIsSyncing(true);
      await triggerSync();
      // Reload queue after sync call
      await loadQueue();
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

  return (
    <div style={{ padding: "24px", maxWidth: "1600px", margin: "0 auto" }}>
      <Header
        stats={stats}
        onSync={handleSync}
        isSyncing={isSyncing}
        theme={theme}
        onToggleTheme={toggleTheme}
      />

      <main>
        {view === "master" ? (
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
              setSelectedShipment(null);
              loadQueue(); // Refresh queue when returning
            }}
          />
        )}
      </main>
    </div>
  );
}

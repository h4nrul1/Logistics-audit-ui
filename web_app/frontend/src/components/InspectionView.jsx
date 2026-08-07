import React, { useState, useEffect } from "react";
import { ArrowLeft, Loader2 } from "lucide-react";
import PdfViewer from "./PdfViewer";
import AnomaliesPanel from "./AnomaliesPanel";
import CorrectionsForm from "./CorrectionsForm";
import { fetchShipmentDetail, saveOverrides, resetOverrides } from "../services/api";

export default function InspectionView({ shipmentId, onBack }) {
  const [loading, setLoading] = useState(true);
  const [detailData, setDetailData] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [resettingDoc, setResettingDoc] = useState(null);
  const [saveMessage, setSaveMessage] = useState(null);

  const loadDetail = async () => {
    try {
      setLoading(true);
      const data = await fetchShipmentDetail(shipmentId);
      setDetailData(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (shipmentId) {
      loadDetail();
    }
  }, [shipmentId]);

  const handleResetOverride = async (docType) => {
    if (!window.confirm(`Are you sure you want to reset all audit corrections for ${docType}? This will delete the audited PDF and restore original extracted values.`)) {
      return;
    }
    try {
      setResettingDoc(docType);
      setSaveMessage(null);
      const result = await resetOverrides(shipmentId, docType);
      setSaveMessage(`✅ ${result.message || `Reset ${docType} corrections successfully.`}`);
      await loadDetail();
    } catch (err) {
      console.error(err);
      setSaveMessage(`❌ Error resetting ${docType} corrections: ${err.message}`);
    } finally {
      setResettingDoc(null);
    }
  };

  const isValDifferent = (val1, val2) => {
    if (val1 === undefined || val1 === null) val1 = "";
    if (val2 === undefined || val2 === null) val2 = "";
    if (val1 === "" && val2 === "") return false;
    
    // Numeric comparison
    const n1 = Number(val1);
    const n2 = Number(val2);
    if (!isNaN(n1) && !isNaN(n2) && String(val1).trim() !== "" && String(val2).trim() !== "") {
      return Math.abs(n1 - n2) > 0.0001;
    }
    
    return String(val1).trim() !== String(val2).trim();
  };

  const handleSaveOverrides = async (formState) => {
    try {
      setIsSaving(true);
      setSaveMessage(null);
      
      // Calculate diffs relative to currently loaded document values
      const overridesToSave = {};
      Object.entries(formState).forEach(([dt, newVals]) => {
        const origVals = detailData?.documents?.[dt] || {};
        const diffs = {};

        Object.entries(newVals).forEach(([k, val]) => {
          if (k === "items") return;
          const origVal = origVals[k];
          if (isValDifferent(val, origVal)) {
            diffs[k] = val;
          }
        });

        if (Array.isArray(newVals.items)) {
          newVals.items.forEach((item, idx) => {
            const origItem = origVals.items?.[idx] || {};
            Object.entries(item).forEach(([subKey, subVal]) => {
              const fieldKey = `items_${idx}_${subKey}`;
              const origSubVal = origItem[subKey];
              if (isValDifferent(subVal, origSubVal)) {
                diffs[fieldKey] = subVal;
              }
            });
          });
        }

        if (Object.keys(diffs).length > 0) {
          overridesToSave[dt] = diffs;
        }
      });

      if (Object.keys(overridesToSave).length === 0) {
        setSaveMessage("ℹ️ No changes were detected in any form fields.");
        setIsSaving(false);
        return;
      }

      const result = await saveOverrides(shipmentId, overridesToSave);
      setSaveMessage(`✅ Overrides saved successfully for: ${result.modified_documents?.join(", ") || "documents"}`);
      
      // Reload fresh detail data to update audited PDFs list
      await loadDetail();
    } catch (err) {
      console.error(err);
      setSaveMessage(`❌ Error saving overrides: ${err.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: "48px", textAlign: "center" }}>
        <Loader2 size={36} className="spin-icon" style={{ margin: "0 auto 16px", color: "var(--accent-primary)" }} />
        <p style={{ color: "var(--text-muted)", fontSize: "1rem" }}>Loading shipment inspection data for {shipmentId}...</p>
      </div>
    );
  }

  if (!detailData) {
    return (
      <div className="glass-card" style={{ padding: "32px", textAlign: "center" }}>
        <p style={{ color: "var(--status-failed)" }}>Failed to load shipment details.</p>
        <button className="btn btn-secondary" onClick={onBack} style={{ marginTop: "16px" }}>
          <ArrowLeft size={16} /> Back to Master Queue
        </button>
      </div>
    );
  }

  return (
    <div>
      {/* Back Button & Title Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
        <button className="btn btn-secondary" onClick={onBack}>
          <ArrowLeft size={16} /> Back to Master Queue
        </button>
        <div style={{ textAlign: "right" }}>
          <h2 style={{ fontSize: "1.2rem", fontWeight: "700" }}>Shipment Inspection View</h2>
          <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Shipment ID: <code style={{ color: "var(--accent-primary)" }}>{shipmentId}</code></span>
        </div>
      </div>

      {/* Save Status Notification */}
      {saveMessage && (
        <div style={{ padding: "12px 16px", borderRadius: "8px", marginBottom: "16px", background: "rgba(16, 185, 129, 0.15)", border: "1px solid rgba(16, 185, 129, 0.3)", color: "var(--status-passed)", fontWeight: "600" }}>
          {saveMessage}
        </div>
      )}

      {/* Split-Screen Layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px", alignItems: "start" }}>
        {/* Left Column: PDF Viewer */}
        <div>
          <PdfViewer shipmentId={shipmentId} pdfFiles={detailData.pdf_files || []} />
        </div>

        {/* Right Column: Anomalies & Corrections Form */}
        <div>
          <AnomaliesPanel 
            anomalies={detailData.anomalies || []} 
            indicators={detailData.indicators || {}} 
            foreignCurrency={detailData.indicators?.currency} 
          />
          <CorrectionsForm 
            documents={detailData.documents || {}} 
            pdfFiles={detailData.pdf_files || []}
            onSave={handleSaveOverrides} 
            onReset={handleResetOverride}
            isSaving={isSaving} 
            resettingDoc={resettingDoc}
          />
        </div>
      </div>
    </div>
  );
}

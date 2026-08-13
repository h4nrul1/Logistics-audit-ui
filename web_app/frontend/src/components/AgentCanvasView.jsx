import React, { useState, useEffect, useRef } from "react";
import { Send, Bot, User, Cpu, Sparkles, FileText, RefreshCw, Eye, Wrench, RotateCcw, Square, CheckCircle2, X } from "lucide-react";
import { sendAgentMessage, fetchShipmentDetail, resetOverrides, flagShipmentResolved, reopenShipmentAudit, fetchQueue } from "../services/api";
import PdfViewer from "./PdfViewer";
import AnomaliesPanel from "./AnomaliesPanel";

export default function AgentCanvasView({ 
  selectedShipment, 
  shipmentDetail, 
  onSelectShipment, 
  onRefresh 
}) {
  const [messages, setMessages] = useState([
    {
      role: "agent",
      text: "Hello! I am your **Logistics Audit Master Coordinator Agent** powered by Google ADK.\n\nI can inspect audit anomalies across CIV, PKL, SLI, and VGM documents, explain financial/weight/currency discrepancies, apply supervisor corrections, and generate stamp-certified audited PDFs. How can I assist you today?",
      trajectory: []
    }
  ]);
  const [inputPrompt, setInputPrompt] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isCanvasLoading, setIsCanvasLoading] = useState(false);
  const [activeCanvasTab, setActiveCanvasTab] = useState("pdf"); // "pdf" | "diff"
  const [localShipmentDetail, setLocalShipmentDetail] = useState(null);
  const [allShipmentsList, setAllShipmentsList] = useState([]);

  const chatEndRef = useRef(null);
  const abortControllerRef = useRef(null);

  // Load shipment queue for manual shipment picker dropdown
  useEffect(() => {
    fetchQueue()
      .then((data) => {
        if (data && data.shipments) {
          setAllShipmentsList(data.shipments);
        }
      })
      .catch((err) => console.error("Error loading shipments for picker:", err));
  }, []);

  // Fetch local shipment detail whenever selectedShipment changes
  useEffect(() => {
    if (selectedShipment) {
      setIsCanvasLoading(true);
      setLocalShipmentDetail(null); // Clear stale data immediately
      fetchShipmentDetail(selectedShipment)
        .then((data) => {
          setLocalShipmentDetail(data);
        })
        .catch((err) => console.error("Canvas fetch detail error:", err))
        .finally(() => setIsCanvasLoading(false));
    }
  }, [selectedShipment]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  const handleSendPrompt = async (customPrompt) => {
    const textToSend = customPrompt || inputPrompt;
    if (!textToSend.trim() || isLoading) return;

    const userMsg = { role: "user", text: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const res = await sendAgentMessage(
        textToSend, 
        "web_canvas_session", 
        selectedShipment, 
        "", 
        controller.signal
      );
      
      const agentText = res.response || "Task completed.";
      const agentMsg = {
        role: "agent",
        text: agentText,
        trajectory: res.trajectory || []
      };
      setMessages((prev) => [...prev, agentMsg]);
      
      // Auto refresh app state if agent executed tool calls that mutated state
      if (res.trajectory && res.trajectory.length > 0) {
        onRefresh();
        if (selectedShipment) {
          fetchShipmentDetail(selectedShipment).then((data) => setLocalShipmentDetail(data));
        }
      }
    } catch (err) {
      if (err.name === "AbortError") {
        // Handled by handleStopGeneration
        return;
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: `⚠️ Error executing agent instruction: ${err.message}`,
          trajectory: []
        }
      ]);
    } finally {
      setIsLoading(false);
      setInputPrompt("");
      abortControllerRef.current = null;
    }
  };

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsLoading(false);
    setMessages((prev) => [
      ...prev,
      {
        role: "agent",
        text: "⏹️ Response generation stopped by user. You can edit your prompt below and resend.",
        trajectory: []
      }
    ]);
  };

  const handleResetOverrides = async (docType) => {
    if (!selectedShipment) return;
    try {
      setIsLoading(true);
      await resetOverrides(selectedShipment, docType);
      onRefresh();
      const updatedData = await fetchShipmentDetail(selectedShipment);
      setLocalShipmentDetail(updatedData);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: docType === "ALL" 
            ? `Reset ALL auditor corrections across all documents for shipment **#${selectedShipment}**. Original PDFs restored.`
            : `Reset all auditor corrections for **${docType}** on shipment **#${selectedShipment}**. Original document restored.`,
          trajectory: []
        }
      ]);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleConfirmCompliance = async () => {
    if (!selectedShipment) return;
    try {
      setIsLoading(true);
      await flagShipmentResolved(selectedShipment);
      onRefresh();
      const updatedData = await fetchShipmentDetail(selectedShipment);
      setLocalShipmentDetail(updatedData);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: `✅ **Compliance Confirmed**: Shipment **#${selectedShipment}** has been manually verified by auditor and flagged as **RESOLVED / COMPLIANT** in BigQuery.`,
          trajectory: []
        }
      ]);
    } catch (err) {
      console.error("Compliance flag error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleReopenAudit = async () => {
    if (!selectedShipment) return;
    try {
      setIsLoading(true);
      await reopenShipmentAudit(selectedShipment);
      onRefresh();
      const updatedData = await fetchShipmentDetail(selectedShipment);
      setLocalShipmentDetail(updatedData);
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: `⚠️ **Audit Re-opened**: Shipment **#${selectedShipment}** compliance flag has been reset. The shipment is now re-opened for auditor inspection and further document edits.`,
          trajectory: []
        }
      ]);
    } catch (err) {
      console.error("Re-open audit error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const samplePrompts = [
    `Why did shipment [insert number] fail audit?`,
    `Correct shipment [insert number] and update the audited PDF.`,
    `Show all shipments with weight discrepancies`,
    `Sync Google Drive for new PDF files`
  ];

  // Strictly validate detail matches active selectedShipment ID
  const detailToUse = (localShipmentDetail && String(localShipmentDetail.shipment_id) === String(selectedShipment))
    ? localShipmentDetail 
    : ((shipmentDetail && String(shipmentDetail.shipment_id) === String(selectedShipment)) ? shipmentDetail : null);

  const pdfFiles = detailToUse?.pdf_files || [];
  const anomalies = detailToUse?.anomalies || [];
  const hasAnomalies = anomalies.length > 0;
  const isResolvedShipment = detailToUse?.is_resolved === true || detailToUse?.status === "Resolved";

  // Find document types that ACTUALLY have audited PDFs for this shipment
  const auditedDocTypes = [...new Set(
    (pdfFiles || [])
      .filter(f => f.is_audited || (f.name || f.blob_name || "").toLowerCase().includes("_audited"))
      .map(f => {
        const fname = (f.name || f.blob_name || "").split('/').pop().toLowerCase();
        if (fname.includes("civ")) return "CIV";
        if (fname.includes("pkl")) return "PKL";
        if (fname.includes("sli")) return "SLI";
        if (fname.includes("vgm")) return "VGM";
        return null;
      })
      .filter(Boolean)
  )];

  const isPendingCompliance = detailToUse?.is_pending_compliance === true || detailToUse?.status === "Audited / Pending Compliance" || (auditedDocTypes.length > 0 && !isResolvedShipment && !hasAnomalies);
  const canConfirmCompliance = (hasAnomalies || isPendingCompliance || (auditedDocTypes.length > 0 && !isResolvedShipment)) && !isResolvedShipment;

  // Helper to format text with ANY 8-digit clickable shipment links and markdown bold
  const renderFormattedText = (text) => {
    const parts = text.split(/(\b\d{8}\b|\*\*[^*]+\*\*)/g);
    return parts.map((part, idx) => {
      if (/^\d{8}$/.test(part)) {
        return (
          <button
            key={idx}
            onClick={() => onSelectShipment(part)}
            style={{
              padding: "2px 8px",
              margin: "0 3px",
              borderRadius: "6px",
              background: "rgba(139, 92, 246, 0.25)",
              border: "1px solid rgba(139, 92, 246, 0.5)",
              color: "#38bdf8",
              cursor: "pointer",
              fontWeight: "600",
              fontSize: "0.85rem",
              display: "inline-flex",
              alignItems: "center",
              gap: "4px"
            }}
            title={`Inspect Shipment #${part} on Canvas`}
          >
            <Eye size={12} />
            #{part}
          </button>
        );
      } else if (part.startsWith("**") && part.endsWith("**")) {
        return <strong key={idx}>{part.slice(2, -2)}</strong>;
      }
      return part;
    });
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", height: "calc(100vh - 120px)", minHeight: "650px" }}>
      
      {/* LEFT PANEL: Agent Command & Reasoning Stream */}
      <div className="glass-card" style={{ display: "flex", flexDirection: "column", padding: "20px", borderRadius: "16px", overflow: "hidden" }}>
        
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "16px", paddingBottom: "12px", borderBottom: "1px solid var(--bg-card-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ background: "linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)", padding: "8px", borderRadius: "10px", display: "flex" }}>
              <Bot size={20} color="#fff" />
            </div>
            <div>
              <h2 style={{ fontSize: "1.1rem", fontWeight: "700", margin: 0 }}>Agent Command & Reasoning Stream</h2>
              <span style={{ fontSize: "0.75rem", color: "var(--status-passed)", display: "flex", alignItems: "center", gap: "4px" }}>
                <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "var(--status-passed)", display: "inline-block" }}></span>
                ADK Multi-Agent Orchestrator Active
              </span>
            </div>
          </div>
          <button className="btn btn-secondary" style={{ padding: "6px 12px", fontSize: "0.8rem" }} onClick={onRefresh} title="Refresh Context">
            <RefreshCw size={14} /> Refresh
          </button>
        </div>

        {/* Quick Sample Prompt Chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: "8px", marginBottom: "16px" }}>
          {samplePrompts.map((p, idx) => (
            <button
              key={idx}
              onClick={() => setInputPrompt(p)}
              disabled={isLoading}
              style={{
                fontSize: "0.75rem",
                padding: "6px 12px",
                borderRadius: "20px",
                background: "rgba(139, 92, 246, 0.12)",
                border: "1px solid rgba(139, 92, 246, 0.3)",
                color: "var(--text-main)",
                cursor: "pointer",
                transition: "all 0.2s ease"
              }}
              className="chip-btn"
              title="Click to populate input box for editing"
            >
              <Sparkles size={12} style={{ color: "#a855f7", marginRight: "4px", verticalAlign: "middle" }} />
              {p}
            </button>
          ))}
        </div>

        {/* Chat Stream Body */}
        <div style={{ flex: 1, overflowY: "auto", paddingRight: "8px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {messages.map((m, idx) => (
            <div key={idx} style={{ display: "flex", flexDirection: "column", gap: "6px", alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "92%" }}>
              
              <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.75rem", color: "var(--text-muted)", alignSelf: m.role === "user" ? "flex-end" : "flex-start" }}>
                {m.role === "user" ? (
                  <>You <User size={14} /></>
                ) : (
                  <><Bot size={14} color="#a855f7" /> ADK Master Agent</>
                )}
              </div>

              {/* Message Box */}
              <div style={{
                padding: "14px 16px",
                borderRadius: m.role === "user" ? "16px 16px 2px 16px" : "16px 16px 16px 2px",
                background: m.role === "user" ? "var(--chat-bubble-user-bg)" : "var(--chat-bubble-agent-bg)",
                border: m.role === "user" ? "none" : "1px solid var(--chat-bubble-agent-border)",
                color: m.role === "user" ? "var(--chat-bubble-user-text)" : "var(--chat-bubble-agent-text)",
                fontSize: "0.9rem",
                lineHeight: "1.5",
                whiteSpace: "pre-wrap"
              }}>
                {renderFormattedText(m.text)}
              </div>

              {/* Agent Trajectory / Tool Execution Steps */}
              {m.trajectory && m.trajectory.length > 0 && (
                <div style={{ background: "var(--trajectory-bg)", padding: "10px 14px", borderRadius: "10px", border: "1px solid var(--chat-bubble-agent-border)", fontSize: "0.8rem", marginTop: "4px" }}>
                  <div style={{ fontSize: "0.75rem", fontWeight: "600", color: "#a855f7", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
                    <Cpu size={14} /> Agent Execution Steps ({m.trajectory.length})
                  </div>
                  {m.trajectory.map((step, sIdx) => (
                    <div key={sIdx} style={{ fontSize: "0.75rem", color: "var(--trajectory-text)", fontFamily: "monospace", margin: "3px 0" }}>
                      ⚡ {step.step} {step.arguments ? `(${JSON.stringify(step.arguments)})` : ''}
                    </div>
                  ))}
                </div>
              )}

            </div>
          ))}

          {isLoading && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", borderRadius: "12px", background: "var(--chat-bubble-agent-bg)", border: "1px solid var(--chat-bubble-agent-border)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <RefreshCw size={16} className="spin-icon" color="#a855f7" />
                <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Agent is reasoning & executing tools...</span>
              </div>
              <button
                type="button"
                onClick={handleStopGeneration}
                style={{
                  padding: "6px 12px",
                  borderRadius: "8px",
                  background: "rgba(239, 68, 68, 0.15)",
                  border: "1px solid rgba(239, 68, 68, 0.4)",
                  color: "#f87171",
                  fontSize: "0.78rem",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px"
                }}
              >
                <Square size={12} fill="#f87171" /> Stop Generation
              </button>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Bar */}
        <form 
          onSubmit={(e) => { e.preventDefault(); handleSendPrompt(); }}
          style={{ display: "flex", gap: "10px", marginTop: "16px", paddingTop: "12px", borderTop: "1px solid var(--bg-card-border)", alignItems: "flex-end" }}
        >
          <textarea
            className="form-control"
            placeholder="Ask agent to inspect, override values, sync drive, or reprocess... (Shift+Enter for new line)"
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendPrompt();
              }
            }}
            rows={2}
            style={{
              flex: 1,
              padding: "10px 14px",
              borderRadius: "12px",
              background: "var(--input-bar-bg)",
              border: "1px solid var(--input-bar-border)",
              color: "var(--input-bar-text)",
              fontSize: "0.9rem",
              fontFamily: "inherit",
              resize: "none",
              outline: "none",
              lineHeight: "1.4"
            }}
          />
          <button 
            type="submit" 
            className="btn btn-primary" 
            disabled={!inputPrompt.trim() || isLoading}
            style={{ 
              padding: "12px 20px", 
              borderRadius: "12px", 
              background: "linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)", 
              border: "none",
              height: "46px",
              cursor: (!inputPrompt.trim() || isLoading) ? "not-allowed" : "pointer",
              opacity: (!inputPrompt.trim() || isLoading) ? 0.6 : 1
            }}
          >
            <Send size={18} />
          </button>
        </form>

      </div>


      {/* RIGHT PANEL: Dynamic Context Canvas */}
      <div className="glass-card" style={{ display: "flex", flexDirection: "column", padding: "20px", borderRadius: "16px", overflow: "hidden" }}>
        
        {/* Canvas Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px", paddingBottom: "12px", borderBottom: "1px solid var(--bg-card-border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div>
              <span style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#a855f7", fontWeight: "600" }}>Dynamic Context Canvas</span>
              <h3 style={{ fontSize: "1.1rem", fontWeight: "700", margin: 0 }}>
                {selectedShipment ? `Shipment #${selectedShipment}` : "Select Shipment to Inspect"}
              </h3>
            </div>

            {/* Manual Shipment Picker Dropdown */}
            <select
              value={selectedShipment || ""}
              onChange={(e) => onSelectShipment(e.target.value || null)}
              style={{
                padding: "6px 12px",
                borderRadius: "8px",
                background: "var(--dropdown-bg)",
                border: "1px solid var(--dropdown-border)",
                color: "var(--dropdown-text)",
                fontSize: "0.82rem",
                fontWeight: "600",
                cursor: "pointer"
              }}
            >
              <option value="">-- Manual Select Shipment --</option>
              {allShipmentsList.map((s) => (
                <option key={s.shipment_id} value={s.shipment_id}>
                  Shipment #{s.shipment_id} ({s.status})
                </option>
              ))}
            </select>
          </div>

          {/* Canvas Tabs & Close Button */}
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <div style={{ display: "flex", gap: "6px", background: "rgba(0, 0, 0, 0.15)", padding: "4px", borderRadius: "10px" }}>
              <button
                className={`btn ${activeCanvasTab === "pdf" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "4px 12px", fontSize: "0.8rem" }}
                onClick={() => setActiveCanvasTab("pdf")}
              >
                📄 PDF Viewer
              </button>
              <button
                className={`btn ${activeCanvasTab === "diff" ? "btn-primary" : "btn-secondary"}`}
                style={{ padding: "4px 12px", fontSize: "0.8rem" }}
                onClick={() => setActiveCanvasTab("diff")}
              >
                📊 Anomalies ({anomalies.length})
              </button>
            </div>

            {selectedShipment && (
              <button
                onClick={() => onSelectShipment(null)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "6px 12px",
                  borderRadius: "8px",
                  background: "rgba(239, 68, 68, 0.15)",
                  border: "1px solid rgba(239, 68, 68, 0.35)",
                  color: "#f87171",
                  fontSize: "0.8rem",
                  fontWeight: "600",
                  cursor: "pointer"
                }}
                title="Close document viewer and return to No Shipment Selected"
              >
                <X size={15} /> Close Viewer
              </button>
            )}
          </div>
        </div>

        {/* Agent Canvas Action Bar */}
        {selectedShipment && (
          <div style={{ marginBottom: "14px", padding: "10px 14px", borderRadius: "10px", background: "rgba(139, 92, 246, 0.12)", border: "1px solid rgba(139, 92, 246, 0.25)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px", flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem" }}>
              <Wrench size={15} color="#a855f7" />
              <span><strong>Agent Actions:</strong> {hasAnomalies ? `${anomalies.length} anomaly flag(s) detected` : "Shipment clean / resolved"}</span>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              {/* Reset All button for shipments with multiple audited PDFs */}
              {auditedDocTypes.length > 1 && (
                <button
                  className="btn btn-secondary"
                  style={{
                    padding: "4px 10px",
                    fontSize: "0.78rem",
                    border: "1px solid rgba(239, 68, 68, 0.6)",
                    background: "rgba(239, 68, 68, 0.2)",
                    color: "#f87171",
                    fontWeight: "700"
                  }}
                  onClick={() => handleResetOverrides("ALL")}
                  disabled={isLoading}
                  title="Reset ALL auditor corrections across all document types and restore original PDFs"
                >
                  <RotateCcw size={13} /> Reset All ({auditedDocTypes.length} PDFs)
                </button>
              )}

              {/* Individual Reset buttons */}
              {auditedDocTypes.map((dt) => (
                <button
                  key={dt}
                  className="btn btn-secondary"
                  style={{ padding: "4px 10px", fontSize: "0.78rem", border: "1px solid rgba(239, 68, 68, 0.4)", color: "#f87171" }}
                  onClick={() => handleResetOverrides(dt)}
                  disabled={isLoading}
                  title={`Reset ${dt} corrections and restore original PDF`}
                >
                  <RotateCcw size={13} /> Reset {dt}
                </button>
              ))}

              {/* Confirm Compliance button for shipments WITH active anomalies OR Audited / Pending Compliance */}
              {canConfirmCompliance && (
                <button
                  className="btn btn-primary"
                  style={{
                    padding: "5px 12px",
                    fontSize: "0.78rem",
                    fontWeight: "700",
                    background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                    border: "1px solid #10b981",
                    color: "#ffffff",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    cursor: isLoading ? "default" : "pointer"
                  }}
                  onClick={handleConfirmCompliance}
                  disabled={isLoading}
                  title="Confirm auditor compliance and flag this shipment as resolved in BigQuery"
                >
                  <CheckCircle2 size={14} /> Confirm Compliance & Flag Resolved
                </button>
              )}

              {/* Re-open Audit button ONLY for shipments that are currently FLAGGED AS RESOLVED */}
              {isResolvedShipment && !hasAnomalies && (
                <button
                  className="btn btn-secondary"
                  style={{
                    padding: "5px 12px",
                    fontSize: "0.78rem",
                    fontWeight: "700",
                    background: "rgba(245, 158, 11, 0.18)",
                    border: "1px solid rgba(245, 158, 11, 0.5)",
                    color: "#f59e0b",
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    cursor: isLoading ? "default" : "pointer"
                  }}
                  onClick={handleReopenAudit}
                  disabled={isLoading}
                  title="Re-open this resolved shipment for further auditing and document changes"
                >
                  <RotateCcw size={14} /> Re-open Audit for Editing
                </button>
              )}
            </div>
          </div>
        )}

        {/* Canvas Body */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {!selectedShipment ? (
            <div style={{ height: "100%", minHeight: "420px", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", color: "var(--text-muted)", gap: "16px", padding: "40px 24px", background: "var(--placeholder-bg)", borderRadius: "12px", border: "1px dashed var(--bg-card-border)" }}>
              <div style={{ background: "rgba(139, 92, 246, 0.1)", padding: "16px", borderRadius: "50%", border: "1px solid rgba(139, 92, 246, 0.2)" }}>
                <FileText size={40} color="#a855f7" />
              </div>
              <h4 style={{ margin: 0, color: "var(--text-main)", fontSize: "1.05rem", fontWeight: "600" }}>No Shipment Selected</h4>
              <p style={{ fontSize: "0.85rem", color: "var(--text-muted)", maxWidth: "380px", margin: 0, lineHeight: "1.5" }}>
                Select a shipment using the dropdown above or click on a shipment hyperlink (e.g. <em>#10386317</em>) in the agent response to load documents.
              </p>
            </div>
          ) : isCanvasLoading ? (
            <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", color: "var(--text-muted)", gap: "10px" }}>
              <RefreshCw size={24} className="spin-icon" color="#a855f7" />
              <p style={{ fontSize: "0.9rem" }}>Loading PDFs & GCS blobs for Shipment #{selectedShipment}...</p>
            </div>
          ) : activeCanvasTab === "pdf" ? (
            <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
              <PdfViewer
                shipmentId={selectedShipment}
                pdfFiles={pdfFiles}
              />
            </div>
          ) : (
            <div>
              <AnomaliesPanel anomalies={anomalies} />
            </div>
          )}
        </div>

      </div>

    </div>
  );
}


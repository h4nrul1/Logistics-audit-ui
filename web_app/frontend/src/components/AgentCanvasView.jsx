import React, { useState, useEffect, useRef } from "react";
import { Send, Bot, User, Cpu, Sparkles, CheckCircle2, FileText, RefreshCw, Eye, Wrench, RotateCcw } from "lucide-react";
import { sendAgentMessage, fetchShipmentDetail, resetOverrides } from "../services/api";
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

  const chatEndRef = useRef(null);

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

  // Extract ANY 8-digit shipment ID from text
  const extractShipmentId = (text) => {
    const match = text.match(/\b(\d{8})\b/);
    return match ? match[1] : null;
  };

  const handleSendPrompt = async (customPrompt) => {
    const textToSend = customPrompt || inputPrompt;
    if (!textToSend.trim() || isLoading) return;

    // Check if prompt contains an 8-digit shipment ID and update canvas selection
    const extractedId = extractShipmentId(textToSend);
    if (extractedId && extractedId !== selectedShipment) {
      onSelectShipment(extractedId);
    }

    const userMsg = { role: "user", text: textToSend };
    setMessages((prev) => [...prev, userMsg]);
    if (!customPrompt) setInputPrompt("");
    setIsLoading(true);

    try {
      const res = await sendAgentMessage(textToSend, "web_canvas_session", selectedShipment);
      const agentText = res.response || "Task completed.";
      const agentMsg = {
        role: "agent",
        text: agentText,
        trajectory: res.trajectory || []
      };
      setMessages((prev) => [...prev, agentMsg]);
      
      // Auto-extract shipment ID from agent response if present
      const respExtractedId = extractShipmentId(agentText);
      if (respExtractedId && respExtractedId !== selectedShipment) {
        onSelectShipment(respExtractedId);
      }

      // Auto refresh app state if agent executed tool calls that mutated state
      if (res.trajectory && res.trajectory.length > 0) {
        onRefresh();
        if (selectedShipment) {
          fetchShipmentDetail(selectedShipment).then((data) => setLocalShipmentDetail(data));
        }
      }
    } catch (err) {
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
    }
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
          text: `Reset all auditor corrections for **${docType}** on shipment **${selectedShipment}**. Original document restored.`,
          trajectory: []
        }
      ]);
    } catch (err) {
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  };

  const samplePrompts = [
    `Why did shipment ${selectedShipment || '10386317'} fail audit?`,
    `Show all shipments with weight discrepancies`,
    `Sync Google Drive for new PDF files`,
    `Reprocess all past shipments with original timestamps`
  ];

  // Strictly validate detail matches active selectedShipment ID
  const detailToUse = (localShipmentDetail && String(localShipmentDetail.shipment_id) === String(selectedShipment))
    ? localShipmentDetail 
    : ((shipmentDetail && String(shipmentDetail.shipment_id) === String(selectedShipment)) ? shipmentDetail : null);

  const pdfFiles = detailToUse?.pdf_files || [];
  const anomalies = detailToUse?.anomalies || [];
  const hasAnomalies = anomalies.length > 0;

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
              onClick={() => handleSendPrompt(p)}
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
            >
              <Sparkles size={12} style={{ color: "#a855f7", marginRight: "4px", verticalAlign: "middle" }} />
              {p}
            </button>
          ))}
        </div>

        {/* Chat Stream Body */}
        <div style={{ flex: 1, overflowY: "auto", paddingRight: "8px", display: "flex", flexDirection: "column", gap: "16px" }}>
          {messages.map((m, idx) => {
            const lowerText = m.text.toLowerCase();
            const isProposal = m.role === "agent" && (
              lowerText.includes("proceed") ||
              lowerText.includes("correction") ||
              lowerText.includes("would you like me to") ||
              lowerText.includes("shall i") ||
              lowerText.includes("apply this") ||
              lowerText.includes("correct the")
            );

            return (
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
                  background: m.role === "user" ? "var(--accent-blue)" : "rgba(30, 41, 59, 0.8)",
                  border: m.role === "user" ? "none" : "1px solid var(--bg-card-border)",
                  color: "#ffffff",
                  fontSize: "0.9rem",
                  lineHeight: "1.5",
                  whiteSpace: "pre-wrap"
                }}>
                  {renderFormattedText(m.text)}

                  {/* Interactive Action Card if Agent Proposes Fix */}
                  {isProposal && (
                    <div style={{ marginTop: "12px", paddingTop: "10px", borderTop: "1px solid rgba(255, 255, 255, 0.1)", display: "flex", gap: "10px" }}>
                      <button
                        className="btn btn-primary"
                        style={{ padding: "8px 16px", fontSize: "0.82rem", background: "linear-gradient(135deg, #059669 0%, #10b981 100%)", border: "none", cursor: "pointer" }}
                        onClick={() => handleSendPrompt(`Yes, please proceed with the correction for shipment ${selectedShipment || ''} and update the audited PDF certificate.`)}
                      >
                        <CheckCircle2 size={15} /> Yes, Apply Fix & Update PDF
                      </button>
                    </div>
                  )}
                </div>

                {/* Agent Trajectory / Tool Execution Steps */}
                {m.trajectory && m.trajectory.length > 0 && (
                  <div style={{ background: "rgba(15, 23, 42, 0.6)", padding: "10px 14px", borderRadius: "10px", border: "1px solid rgba(139, 92, 246, 0.3)", fontSize: "0.8rem", marginTop: "4px" }}>
                    <div style={{ fontSize: "0.75rem", fontWeight: "600", color: "#a855f7", marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px" }}>
                      <Cpu size={14} /> Agent Execution Steps ({m.trajectory.length})
                    </div>
                    {m.trajectory.map((step, sIdx) => (
                      <div key={sIdx} style={{ fontSize: "0.75rem", color: "var(--text-dim)", fontFamily: "monospace", margin: "3px 0" }}>
                        ⚡ {step.step} {step.arguments ? `(${JSON.stringify(step.arguments)})` : ''}
                      </div>
                    ))}
                  </div>
                )}

              </div>
            );
          })}

          {isLoading && (
            <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px 16px", borderRadius: "12px", background: "rgba(30, 41, 59, 0.5)", width: "fit-content" }}>
              <RefreshCw size={16} className="spin-icon" color="#a855f7" />
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Agent is reasoning & executing tools...</span>
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input Bar */}
        <form 
          onSubmit={(e) => { e.preventDefault(); handleSendPrompt(); }}
          style={{ display: "flex", gap: "10px", marginTop: "16px", paddingTop: "12px", borderTop: "1px solid var(--bg-card-border)" }}
        >
          <input
            type="text"
            className="form-control"
            placeholder="Ask agent to inspect, override values, sync drive, or reprocess..."
            value={inputPrompt}
            onChange={(e) => setInputPrompt(e.target.value)}
            disabled={isLoading}
            style={{ flex: 1, padding: "12px 16px", borderRadius: "12px", background: "rgba(15, 23, 42, 0.8)", border: "1px solid var(--bg-card-border)", color: "#fff" }}
          />
          <button 
            type="submit" 
            className="btn btn-primary" 
            disabled={isLoading || !inputPrompt.trim()}
            style={{ padding: "12px 20px", borderRadius: "12px", background: "linear-gradient(135deg, #8b5cf6 0%, #ec4899 100%)", border: "none" }}
          >
            <Send size={18} />
          </button>
        </form>

      </div>


      {/* RIGHT PANEL: Dynamic Context Canvas */}
      <div className="glass-card" style={{ display: "flex", flexDirection: "column", padding: "20px", borderRadius: "16px", overflow: "hidden" }}>
        
        {/* Canvas Header */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "12px", paddingBottom: "12px", borderBottom: "1px solid var(--bg-card-border)" }}>
          <div>
            <span style={{ fontSize: "0.75rem", textTransform: "uppercase", color: "#a855f7", fontWeight: "600" }}>Dynamic Context Canvas</span>
            <h3 style={{ fontSize: "1.1rem", fontWeight: "700", margin: 0 }}>
              Shipment #{selectedShipment || "None Selected"}
            </h3>
          </div>

          {/* Canvas Tabs */}
          <div style={{ display: "flex", gap: "6px", background: "rgba(0, 0, 0, 0.2)", padding: "4px", borderRadius: "10px" }}>
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
        </div>

        {/* Agent Canvas Action Bar */}
        {selectedShipment && (
          <div style={{ marginBottom: "14px", padding: "10px 14px", borderRadius: "10px", background: "rgba(139, 92, 246, 0.12)", border: "1px solid rgba(139, 92, 246, 0.25)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "6px", fontSize: "0.8rem" }}>
              <Wrench size={15} color="#a855f7" />
              <span><strong>Agent Actions:</strong> {hasAnomalies ? `${anomalies.length} anomaly flag(s) detected` : "Shipment clean / resolved"}</span>
            </div>

            <div style={{ display: "flex", gap: "8px" }}>
              {hasAnomalies && (
                <button
                  className="btn btn-primary"
                  style={{ padding: "4px 10px", fontSize: "0.78rem", background: "linear-gradient(135deg, #059669 0%, #10b981 100%)", border: "none" }}
                  onClick={() => handleSendPrompt(`Fix discrepancies on shipment ${selectedShipment} and update audited PDF`)}
                  disabled={isLoading}
                >
                  <Sparkles size={13} /> Auto-Fix Discrepancies
                </button>
              )}

              {/* Render Reset buttons ONLY for document types that actually have audited PDFs */}
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
            </div>
          </div>
        )}

        {/* Canvas Body */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {!selectedShipment ? (
            <div style={{ height: "100%", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center", color: "var(--text-muted)", gap: "12px" }}>
              <FileText size={48} color="var(--text-dim)" />
              <p>No shipment selected. Select a shipment from the queue or ask the agent to inspect one!</p>
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

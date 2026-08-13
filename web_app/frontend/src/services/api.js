const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api";

export async function fetchQueue() {
  const res = await fetch(`${API_BASE_URL}/queue`);
  if (!res.ok) {
    throw new Error(`Failed to fetch queue: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchShipmentDetail(shipmentId) {
  const res = await fetch(`${API_BASE_URL}/shipments/${shipmentId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch shipment detail: ${res.statusText}`);
  }
  return res.json();
}

export function getPdfStreamUrl(shipmentId, blobName) {
  return `${API_BASE_URL}/shipments/${shipmentId}/pdf?blob_name=${encodeURIComponent(blobName)}`;
}

export async function saveOverrides(shipmentId, overrides) {
  const res = await fetch(`${API_BASE_URL}/shipments/${shipmentId}/overrides`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ overrides }),
  });
  if (!res.ok) {
    throw new Error(`Failed to save overrides: ${res.statusText}`);
  }
  return res.json();
}

export async function triggerSync() {
  const res = await fetch(`${API_BASE_URL}/sync`, { method: "POST" });
  if (!res.ok) {
    throw new Error(`Failed to trigger sync: ${res.statusText}`);
  }
  return res.json();
}

export async function resetOverrides(shipmentId, docType) {
  const res = await fetch(`${API_BASE_URL}/shipments/${shipmentId}/overrides/${docType}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to reset ${docType} overrides`);
  }
  return res.json();
}

export async function flagShipmentResolved(shipmentId) {
  const res = await fetch(`${API_BASE_URL}/shipments/${shipmentId}/resolve`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to flag shipment as resolved");
  }
  return res.json();
}

export async function reopenShipmentAudit(shipmentId) {
  const res = await fetch(`${API_BASE_URL}/shipments/${shipmentId}/reopen`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to re-open shipment audit");
  }
  return res.json();
}

// --- Agent & IAP Session API Service ---

export async function fetchAuthUser(devEmail = "") {
  const headers = {};
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const res = await fetch(`${API_BASE_URL}/auth/me`, { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch auth user: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchUserSessions(devEmail = "") {
  const headers = {};
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const res = await fetch(`${API_BASE_URL}/agent/sessions`, { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch sessions: ${res.statusText}`);
  }
  return res.json();
}

export async function createNewSession(title = "", devEmail = "") {
  const headers = { "Content-Type": "application/json" };
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const res = await fetch(`${API_BASE_URL}/agent/sessions`, {
    method: "POST",
    headers,
    body: JSON.stringify({ title }),
  });
  if (!res.ok) {
    throw new Error(`Failed to create session: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSessionMessages(sessionId, devEmail = "") {
  const headers = {};
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const res = await fetch(`${API_BASE_URL}/agent/sessions/${sessionId}/messages`, { headers });
  if (!res.ok) {
    throw new Error(`Failed to fetch session messages: ${res.statusText}`);
  }
  return res.json();
}

export async function deleteSession(sessionId, devEmail = "") {
  const headers = {};
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const res = await fetch(`${API_BASE_URL}/agent/sessions/${sessionId}`, {
    method: "DELETE",
    headers,
  });
  if (!res.ok) {
    throw new Error(`Failed to delete session: ${res.statusText}`);
  }
  return res.json();
}

export async function sendAgentMessage(message, sessionId = "", currentShipmentId = "", devEmail = "", signal = null) {
  const headers = { "Content-Type": "application/json" };
  if (devEmail) {
    headers["x-dev-user-email"] = devEmail;
  }
  const options = {
    method: "POST",
    headers,
    body: JSON.stringify({
      message,
      session_id: sessionId,
      current_shipment_id: currentShipmentId,
    }),
  };
  if (signal) {
    options.signal = signal;
  }
  const res = await fetch(`${API_BASE_URL}/agent/chat`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Agent request failed: ${res.statusText}`);
  }
  return res.json();
}

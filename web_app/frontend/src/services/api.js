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

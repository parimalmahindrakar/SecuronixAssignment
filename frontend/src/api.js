async function call(path, opts = {}) {
  const res = await fetch("/api" + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}
export const getQuota = () => call("/quota");
export const getLookup = (id) => call(`/enrichment/${id}`);
export const runLookup = (id) => call(`/enrichment/${id}/run`, { method: "POST" });
export const requestEnrichment = (indicator, analyst_id, key) =>
  call("/enrichment", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify({ indicator, analyst_id }),
  });

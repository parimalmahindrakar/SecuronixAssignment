import { useEffect, useRef, useState } from "react";
import { getQuota, getLookup, requestEnrichment, runLookup } from "./api.js";

const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

export default function App() {
  const [quota, setQuota] = useState(null);
  const [analyst, setAnalyst] = useState("analyst-1");
  const [indicator, setIndicator] = useState("");
  const [lookup, setLookup] = useState(null);
  const [expiresAt, setExpiresAt] = useState(null); // local ms timestamp
  const [left, setLeft] = useState(0);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pendingKey = useRef(null); // reused if the same submit is retried

  const apply = (l) => {
    setLookup(l);
    if (l.seconds_left != null) setExpiresAt(Date.now() + l.seconds_left * 1000);
  };

  // Poll quota dashboard
  useEffect(() => {
    const t = setInterval(() => getQuota().then(setQuota).catch(() => {}), 1500);
    getQuota().then(setQuota).catch((e) => setError(e.message));
    return () => clearInterval(t);
  }, []);

  // Poll status while the request is still active
  const active = lookup && ["queued", "leased", "running"].includes(lookup.status);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => getLookup(lookup.id).then(apply).catch(() => {}), 1000);
    return () => clearInterval(t);
  }, [lookup?.id, active]);

  // Countdown ticker
  useEffect(() => {
    if (lookup?.status !== "leased") return;
    const t = setInterval(() => setLeft(Math.max(0, Math.ceil((expiresAt - Date.now()) / 1000))), 250);
    return () => clearInterval(t);
  }, [lookup?.status, expiresAt]);

  async function submit(e) {
    e.preventDefault();
    setError(""); setBusy(true);
    pendingKey.current ??= crypto.randomUUID();
    try {
      apply(await requestEnrichment(indicator, analyst, pendingKey.current));
      pendingKey.current = null; // success: next submit is a new request
    } catch (err) { setError(err.message); } // key kept -> a retry cannot double-charge
    finally { setBusy(false); }
  }

  async function run() {
    setError(""); setBusy(true);
    try { apply(await runLookup(lookup.id)); getQuota().then(setQuota); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  return (
    <main>
      <h1>Threat-intel enrichment quota</h1>

      <section>
        <h2>Today's quota</h2>
        {quota ? (
          <p className="quota">
            <b>{quota.available}</b> of {quota.total} available · {quota.leased} reserved · {quota.used} used · {quota.queued} waiting
          </p>
        ) : <p>Loading…</p>}
      </section>

      <section>
        <h2>Request enrichment</h2>
        <form onSubmit={submit}>
          <input value={analyst} onChange={(e) => setAnalyst(e.target.value)} placeholder="Analyst id" required />
          <input value={indicator} onChange={(e) => setIndicator(e.target.value)}
                 placeholder="IP, domain or file hash" required />
          <button disabled={busy || active}>Request lookup</button>
        </form>
        {error && <p className="msg error">{error}</p>}
      </section>

      {lookup && (
        <section>
          <h2>Request for <code>{lookup.indicator}</code></h2>
          {lookup.shared && <p className="msg">Someone already has an active lookup for this indicator. You're sharing it, no extra quota used.</p>}

          {lookup.status === "queued" && (
            <p className="msg">Queued. You are position <b>#{lookup.position}</b>. This page updates when a unit frees up.</p>
          )}
          {lookup.status === "leased" && (
            <>
              <p className="msg">Unit reserved. Run the lookup within <b className="timer">{fmt(left)}</b> or the unit goes to the next person.</p>
              <button onClick={run} disabled={busy}>Run lookup</button>
            </>
          )}
          {lookup.status === "running" && <p className="msg">Running lookup…</p>}
          {lookup.status === "expired" && (
            <p className="msg error">Lease expired. The unit was returned. Request again to rejoin.</p>
          )}
          {lookup.status === "completed" && (
            <div className="msg ok">
              <p>Completed. Verdict: <b className={lookup.verdict.verdict}>{lookup.verdict.verdict}</b> (score {lookup.verdict.score}/100)</p>
              <p>Malware families: {lookup.verdict.malware_families.join(", ") || "none"}</p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

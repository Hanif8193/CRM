import { useState, useEffect, useCallback } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ── Shared nav ────────────────────────────────────────────────────────────────

function Header() {
  return (
    <header className="bg-white border-b border-slate-200 shadow-sm">
      <div className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white font-bold text-lg select-none">
            F
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900 leading-none">Flowdesk</p>
            <p className="text-xs text-slate-500 mt-0.5">Analytics Dashboard</p>
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm">
          <a href="/" className="text-slate-500 hover:text-slate-800 transition">Support</a>
          <a href="/dashboard" className="font-medium text-brand-600">Dashboard</a>
          <a href="/admin" className="text-slate-500 hover:text-slate-800 transition">Admin</a>
        </nav>
      </div>
    </header>
  );
}

// ── Metric card ───────────────────────────────────────────────────────────────

function MetricCard({ label, value, sub, color = "brand" }) {
  const colors = {
    brand:   "bg-brand-50  border-brand-100  text-brand-700",
    green:   "bg-emerald-50 border-emerald-100 text-emerald-700",
    amber:   "bg-amber-50  border-amber-100   text-amber-700",
    red:     "bg-red-50    border-red-100     text-red-700",
    slate:   "bg-slate-50  border-slate-200   text-slate-700",
    violet:  "bg-violet-50 border-violet-100  text-violet-700",
  };
  return (
    <div className={`rounded-2xl border px-6 py-5 ${colors[color]}`}>
      <p className="text-xs font-semibold uppercase tracking-wide opacity-70 mb-1">{label}</p>
      <p className="text-3xl font-bold leading-none">{value}</p>
      {sub && <p className="text-xs mt-1.5 opacity-60">{sub}</p>}
    </div>
  );
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function RateBar({ label, value, color }) {
  const pct = parseFloat(value) || 0;
  const barColors = {
    green:  "bg-emerald-500",
    amber:  "bg-amber-500",
    red:    "bg-red-500",
    brand:  "bg-brand-500",
    violet: "bg-violet-500",
    slate:  "bg-slate-400",
  };
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-semibold text-slate-800">{value}</span>
      </div>
      <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${barColors[color]}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [metrics, setMetrics]   = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/metrics`);
      if (!res.ok) throw new Error(`Server returned ${res.status}`);
      const data = await res.json();
      setMetrics(data);
      setLastUpdated(new Date());
      setError("");
    } catch (e) {
      setError("Could not load metrics — is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load + auto-refresh every 30 seconds
  useEffect(() => {
    fetchMetrics();
    const id = setInterval(fetchMetrics, 30_000);
    return () => clearInterval(id);
  }, [fetchMetrics]);

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 mx-auto w-full max-w-5xl px-4 py-10 space-y-8">

        {/* Page title */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">AI Agent Metrics</h1>
            <p className="text-sm text-slate-500 mt-0.5">Live counters — resets on server restart</p>
          </div>
          <button
            onClick={fetchMetrics}
            disabled={loading}
            className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm
                       font-medium text-slate-700 shadow-sm hover:bg-slate-50 transition
                       disabled:opacity-50"
          >
            {loading ? "Loading…" : "Refresh"}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="rounded-xl bg-red-50 border border-red-200 px-5 py-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Skeleton while loading */}
        {loading && !metrics && (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="rounded-2xl border border-slate-200 bg-white px-6 py-5 animate-pulse">
                <div className="h-3 w-20 rounded bg-slate-200 mb-3" />
                <div className="h-8 w-16 rounded bg-slate-200" />
              </div>
            ))}
          </div>
        )}

        {metrics && (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <MetricCard
                label="Total Requests"
                value={metrics.total.toLocaleString()}
                sub="since last server restart"
                color="brand"
              />
              <MetricCard
                label="Cache Hits"
                value={metrics.cache_hits.toLocaleString()}
                sub={metrics.cache_hit_rate + " hit rate"}
                color="green"
              />
              <MetricCard
                label="Escalations"
                value={metrics.escalation.toLocaleString()}
                sub={metrics.escalation_rate + " escalation rate"}
                color="amber"
              />
              <MetricCard
                label="AI (Claude) Calls"
                value={metrics.claude.toLocaleString()}
                sub={metrics.claude_rate + " of requests"}
                color="violet"
              />
              <MetricCard
                label="Docs Served"
                value={metrics.docs.toLocaleString()}
                sub={metrics.docs_rate + " of requests"}
                color="slate"
              />
              <MetricCard
                label="Fallbacks"
                value={metrics.fallback.toLocaleString()}
                sub={metrics.fallback_rate + " fallback rate"}
                color="red"
              />
            </div>

            {/* Rate bars */}
            <div className="rounded-2xl border border-slate-200 bg-white px-6 py-6 shadow-sm">
              <h2 className="text-base font-semibold text-slate-800 mb-5">Request Breakdown</h2>
              <div className="space-y-4">
                <RateBar label="Cache Hit Rate"   value={metrics.cache_hit_rate}  color="green" />
                <RateBar label="Docs Served Rate" value={metrics.docs_rate}       color="brand" />
                <RateBar label="Claude Call Rate" value={metrics.claude_rate}     color="violet" />
                <RateBar label="Escalation Rate"  value={metrics.escalation_rate} color="amber" />
                <RateBar label="Fallback Rate"    value={metrics.fallback_rate}   color="red" />
              </div>
            </div>

            {/* Efficiency insight */}
            <div className="rounded-2xl border border-slate-200 bg-white px-6 py-5 shadow-sm">
              <h2 className="text-base font-semibold text-slate-800 mb-1">Cost Efficiency</h2>
              <p className="text-sm text-slate-500">
                {metrics.total > 0
                  ? `${metrics.cache_hit_rate} of requests were answered instantly from cache — saving Claude API calls.
                     ${metrics.docs_rate} were resolved from product docs without AI.
                     Only ${metrics.claude_rate} required a Claude API call.`
                  : "No requests yet. Start a conversation to see metrics here."}
              </p>
            </div>

            {lastUpdated && (
              <p className="text-xs text-center text-slate-400">
                Last updated: {lastUpdated.toLocaleTimeString()} · Auto-refreshes every 30s
              </p>
            )}
          </>
        )}
      </main>

      <footer className="py-4 text-center text-xs text-slate-400">
        Flowdesk AI · Internal Dashboard
      </footer>
    </div>
  );
}

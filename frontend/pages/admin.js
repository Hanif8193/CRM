import { useState, useEffect, useCallback } from "react";

const API_URL   = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const ADMIN_URL = `${API_URL}/admin`;

// ── Nav ───────────────────────────────────────────────────────────────────────

function Header() {
  return (
    <header className="bg-white border-b border-slate-200 shadow-sm">
      <div className="mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white font-bold text-lg select-none">
            F
          </div>
          <div>
            <p className="text-sm font-semibold text-slate-900 leading-none">Flowdesk</p>
            <p className="text-xs text-slate-500 mt-0.5">Admin Panel</p>
          </div>
        </div>
        <nav className="flex items-center gap-4 text-sm">
          <a href="/" className="text-slate-500 hover:text-slate-800 transition">Support</a>
          <a href="/dashboard" className="text-slate-500 hover:text-slate-800 transition">Dashboard</a>
          <a href="/admin" className="font-medium text-brand-600">Admin</a>
        </nav>
      </div>
    </header>
  );
}

// ── Badges ────────────────────────────────────────────────────────────────────

function StatusBadge({ status }) {
  const map = {
    open:      "bg-blue-100 text-blue-700",
    escalated: "bg-amber-100 text-amber-700",
    closed:    "bg-slate-100 text-slate-500",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[status] || map.open}`}>
      {status}
    </span>
  );
}

function PriorityBadge({ priority }) {
  const map = {
    low:      "bg-slate-100 text-slate-500",
    medium:   "bg-sky-100   text-sky-700",
    high:     "bg-orange-100 text-orange-700",
    critical: "bg-red-100   text-red-700",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[priority] || map.low}`}>
      {priority}
    </span>
  );
}

function ChannelBadge({ channel }) {
  const map = {
    web:      "bg-brand-50 text-brand-700",
    email:    "bg-violet-50 text-violet-700",
    whatsapp: "bg-emerald-50 text-emerald-700",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[channel] || "bg-slate-100 text-slate-500"}`}>
      {channel}
    </span>
  );
}

// ── Conversation messages modal ───────────────────────────────────────────────

function ConversationModal({ sessionId, onClose }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState("");

  useEffect(() => {
    fetch(`${ADMIN_URL}/conversations/${sessionId}/messages`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setMessages(d.messages || []))
      .catch(() => setError("Failed to load messages"))
      .finally(() => setLoading(false));
  }, [sessionId]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg flex flex-col" style={{ maxHeight: "80vh" }}>
        {/* Modal header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div>
            <p className="font-semibold text-slate-800 text-sm">Conversation</p>
            <p className="text-xs text-slate-400 font-mono mt-0.5">{sessionId}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 transition"
          >
            <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3">
          {loading && <p className="text-sm text-slate-400 text-center py-4">Loading…</p>}
          {error   && <p className="text-sm text-red-600 text-center py-4">{error}</p>}
          {!loading && messages.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-4">No messages found</p>
          )}
          {messages.map((msg, i) => {
            const isUser = msg.role === "user";
            return (
              <div key={i} className={`flex flex-col gap-0.5 ${isUser ? "items-end" : "items-start"}`}>
                <span className="text-[10px] text-slate-400 px-1">{isUser ? "Customer" : "AI Agent"}</span>
                <div
                  className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed
                    ${isUser
                      ? "bg-brand-600 text-white rounded-tr-sm"
                      : "bg-slate-100 text-slate-800 rounded-tl-sm"
                    }`}
                >
                  {msg.text}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Tickets tab ───────────────────────────────────────────────────────────────

function TicketsTab() {
  const [tickets, setTickets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [closing, setClosing] = useState(null);

  const fetchTickets = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${ADMIN_URL}/tickets?limit=100`);
      if (!res.ok) throw new Error(res.status);
      const data = await res.json();
      setTickets(data.tickets || []);
      setError("");
    } catch (e) {
      setError("Could not load tickets — is the database connected?");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTickets(); }, [fetchTickets]);

  async function closeTicket(id) {
    setClosing(id);
    try {
      const res = await fetch(`${ADMIN_URL}/tickets/${id}/close`, { method: "PATCH" });
      if (!res.ok) throw new Error(res.status);
      setTickets((prev) =>
        prev.map((t) => (t.id === id ? { ...t, status: "closed" } : t))
      );
    } catch {
      alert(`Failed to close ticket #${id}`);
    } finally {
      setClosing(null);
    }
  }

  if (loading) return <LoadingRows />;
  if (error)   return <ErrorBox message={error} />;
  if (tickets.length === 0) return <EmptyState message="No tickets yet" />;

  const open      = tickets.filter((t) => t.status !== "closed").length;
  const escalated = tickets.filter((t) => t.status === "escalated").length;

  return (
    <div className="space-y-5">
      {/* Summary */}
      <div className="flex gap-4 text-sm">
        <span className="rounded-full bg-blue-100 text-blue-700 px-3 py-1 font-semibold">
          {open} open
        </span>
        <span className="rounded-full bg-amber-100 text-amber-700 px-3 py-1 font-semibold">
          {escalated} escalated
        </span>
        <span className="rounded-full bg-slate-100 text-slate-600 px-3 py-1 font-semibold">
          {tickets.length} total
        </span>
      </div>

      {/* Table */}
      <div className="rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs text-slate-500 uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-3">#</th>
              <th className="text-left px-4 py-3">Customer</th>
              <th className="text-left px-4 py-3">Status</th>
              <th className="text-left px-4 py-3">Priority</th>
              <th className="text-left px-4 py-3">Reason</th>
              <th className="text-left px-4 py-3">Created</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {tickets.map((t) => (
              <tr key={t.id} className="hover:bg-slate-50 transition">
                <td className="px-4 py-3 font-mono text-slate-500">#{t.id}</td>
                <td className="px-4 py-3 text-slate-800 max-w-[160px] truncate">{t.customer_id}</td>
                <td className="px-4 py-3"><StatusBadge status={t.status} /></td>
                <td className="px-4 py-3"><PriorityBadge priority={t.priority} /></td>
                <td className="px-4 py-3 text-slate-500">{t.reason || "—"}</td>
                <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                  {new Date(t.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  {t.status !== "closed" && (
                    <button
                      onClick={() => closeTicket(t.id)}
                      disabled={closing === t.id}
                      className="text-xs font-medium text-slate-500 hover:text-red-600 transition
                                 disabled:opacity-50"
                    >
                      {closing === t.id ? "Closing…" : "Close"}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Conversations tab ─────────────────────────────────────────────────────────

function ConversationsTab() {
  const [convos, setConvos]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");
  const [viewSession, setViewSession] = useState(null);

  useEffect(() => {
    fetch(`${ADMIN_URL}/conversations?limit=50`)
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d) => setConvos(d.conversations || []))
      .catch(() => setError("Could not load conversations — is the database connected?"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingRows />;
  if (error)   return <ErrorBox message={error} />;
  if (convos.length === 0) return <EmptyState message="No conversations yet" />;

  return (
    <>
      {viewSession && (
        <ConversationModal
          sessionId={viewSession}
          onClose={() => setViewSession(null)}
        />
      )}

      <div className="rounded-2xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 border-b border-slate-200 text-xs text-slate-500 uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-3">Customer</th>
              <th className="text-left px-4 py-3">Channel</th>
              <th className="text-left px-4 py-3">Messages</th>
              <th className="text-left px-4 py-3">Last Active</th>
              <th className="text-left px-4 py-3">Started</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {convos.map((c) => (
              <tr key={c.session_id} className="hover:bg-slate-50 transition">
                <td className="px-4 py-3 text-slate-800 max-w-[160px] truncate">{c.customer_id}</td>
                <td className="px-4 py-3"><ChannelBadge channel={c.channel} /></td>
                <td className="px-4 py-3 text-slate-600 font-medium">{c.message_count}</td>
                <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                  {new Date(c.last_active_at).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-slate-400 text-xs whitespace-nowrap">
                  {new Date(c.started_at).toLocaleString()}
                </td>
                <td className="px-4 py-3">
                  <button
                    onClick={() => setViewSession(c.session_id)}
                    className="text-xs font-medium text-brand-600 hover:text-brand-700 transition"
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

// ── Helper components ─────────────────────────────────────────────────────────

function LoadingRows() {
  return (
    <div className="space-y-2 py-4">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="h-10 rounded-lg bg-slate-100 animate-pulse" />
      ))}
    </div>
  );
}

function ErrorBox({ message }) {
  return (
    <div className="rounded-xl bg-red-50 border border-red-200 px-5 py-4 text-sm text-red-700">
      {message}
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div className="rounded-xl bg-slate-50 border border-slate-200 px-5 py-10 text-center text-slate-400 text-sm">
      {message}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

const TABS = ["Tickets", "Conversations"];

export default function Admin() {
  const [activeTab, setActiveTab] = useState("Tickets");

  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 mx-auto w-full max-w-6xl px-4 py-10 space-y-6">

        {/* Page title */}
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Admin Panel</h1>
          <p className="text-sm text-slate-500 mt-0.5">Manage tickets and conversations</p>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-slate-200">
          {TABS.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-5 py-2.5 text-sm font-medium rounded-t-lg transition border-b-2 -mb-px
                ${activeTab === tab
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
                }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        {activeTab === "Tickets"       && <TicketsTab />}
        {activeTab === "Conversations" && <ConversationsTab />}
      </main>

      <footer className="py-4 text-center text-xs text-slate-400">
        Flowdesk AI · Admin Panel
      </footer>
    </div>
  );
}

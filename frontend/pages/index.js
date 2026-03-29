import { useState, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ── Small reusable pieces ─────────────────────────────────────────────────────

function Label({ htmlFor, children }) {
  return (
    <label htmlFor={htmlFor} className="block text-sm font-medium text-slate-700 mb-1">
      {children}
    </label>
  );
}

function Input({ id, type = "text", value, onChange, placeholder, disabled, required }) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={onChange}
      placeholder={placeholder}
      disabled={disabled}
      required={required}
      className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm
                 placeholder-slate-400 shadow-sm transition
                 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/30
                 disabled:bg-slate-100 disabled:cursor-not-allowed"
    />
  );
}

function EscalationBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-0.5
                     text-xs font-semibold text-amber-800">
      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd"
          d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.17
             2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10
             5a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 5zm0 9a1 1
             0 100-2 1 1 0 000 2z"
          clipRule="evenodd" />
      </svg>
      Escalated to human agent
    </span>
  );
}

function ResolvedBadge() {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5
                     text-xs font-semibold text-emerald-800">
      <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20">
        <path fillRule="evenodd"
          d="M16.704 4.153a.75.75 0 01.143 1.052l-8 10.5a.75.75 0 01-1.127.075l-4.5-4.5a.75.75
             0 011.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 011.05-.143z"
          clipRule="evenodd" />
      </svg>
      AI handled
    </span>
  );
}

// ── Chat bubble ───────────────────────────────────────────────────────────────

function formatTime(ts) {
  if (!ts) return "";
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function ChatBubble({ role, text, escalated, isLatest, ts }) {
  const isUser = role === "user";
  return (
    <div className={`flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
      <span className="text-xs font-medium text-slate-400 px-1">
        {isUser ? "You" : "Flowdesk AI"}
        {ts && <span className="ml-1.5 text-slate-300">{formatTime(ts)}</span>}
      </span>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed shadow-sm
          ${isUser
            ? "bg-brand-600 text-white rounded-tr-sm"
            : "bg-white text-slate-800 border border-slate-200 rounded-tl-sm"
          }`}
      >
        {text}
      </div>
      {!isUser && isLatest && (
        <div className="px-1">
          {escalated ? <EscalationBadge /> : <ResolvedBadge />}
        </div>
      )}
    </div>
  );
}

// ── Thinking indicator ────────────────────────────────────────────────────────

function ThinkingBubble() {
  return (
    <div className="flex flex-col items-start gap-1">
      <span className="text-xs font-medium text-slate-400 px-1">Flowdesk AI</span>
      <div className="flex items-center gap-2 rounded-2xl rounded-tl-sm bg-white border
                      border-slate-200 px-4 py-3 shadow-sm">
        <span className="text-sm text-slate-500 italic">Thinking</span>
        <span className="flex gap-0.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Home() {
  // Form fields
  const [name, setName]       = useState("");
  const [email, setEmail]     = useState("");
  const [subject, setSubject] = useState("");
  const [firstMsg, setFirstMsg] = useState("");

  // Chat state
  const [messages, setMessages]   = useState([]);   // { role, text, escalated }
  const [followUp, setFollowUp]   = useState("");
  const [loading, setLoading]     = useState(false);
  const [error, setError]         = useState("");
  const [started, setStarted]     = useState(false); // true after first submit

  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // ── API call ────────────────────────────────────────────────────────────────

  async function sendToAgent(messageText, customerId) {
    const res = await fetch(`${API_URL}/message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        customer_id: customerId,
        channel: "web",
        message: messageText,
      }),
    });
    if (!res.ok) throw new Error(`Server error ${res.status}`);
    return res.json(); // { response, intent, escalated, source }
  }

  // ── First submit (from the contact form) ───────────────────────────────────

  async function handleFormSubmit(e) {
    e.preventDefault();
    setError("");
    setLoading(true);

    const userText = subject ? `[${subject}] ${firstMsg}` : firstMsg;

    setMessages([{ role: "user", text: userText, ts: new Date().toISOString() }]);
    setStarted(true);

    try {
      const data = await sendToAgent(userText, email);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.response, escalated: data.escalated, ts: new Date().toISOString() },
      ]);
    } catch (err) {
      setError("Could not reach the support server. Please try again.");
      setStarted(false);
      setMessages([]);
    } finally {
      setLoading(false);
    }
  }

  // ── Follow-up messages (inside chat view) ─────────────────────────────────

  async function handleFollowUp(e) {
    e.preventDefault();
    if (!followUp.trim()) return;
    setError("");

    const text = followUp.trim();
    setFollowUp("");
    setLoading(true);
    setMessages((prev) => [...prev, { role: "user", text, ts: new Date().toISOString() }]);

    try {
      const data = await sendToAgent(text, email);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: data.response, escalated: data.escalated, ts: new Date().toISOString() },
      ]);
    } catch (err) {
      setError("Message failed to send. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="mx-auto max-w-5xl px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white font-bold text-lg select-none">
              F
            </div>
            <div>
              <p className="text-sm font-semibold text-slate-900 leading-none">Flowdesk</p>
              <p className="text-xs text-slate-500 mt-0.5">Customer Support</p>
            </div>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <a href="/" className="font-medium text-brand-600">Support</a>
            <a href="/dashboard" className="text-slate-500 hover:text-slate-800 transition">Dashboard</a>
            <a href="/admin" className="text-slate-500 hover:text-slate-800 transition">Admin</a>
          </nav>
        </div>
      </header>

      {/* Body */}
      <main className="flex-1 flex items-start justify-center px-4 py-10">
        <div className="w-full max-w-2xl">

          {/* ── Contact form (shown before first submission) ── */}
          {!started && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
              <h1 className="text-xl font-semibold text-slate-900 mb-1">Get support</h1>
              <p className="text-sm text-slate-500 mb-6">
                Fill in the form and our AI agent will reply instantly.
              </p>

              {error && (
                <div className="mb-4 rounded-lg bg-red-50 border border-red-200 px-4 py-3
                                text-sm text-red-700">
                  {error}
                </div>
              )}

              <form onSubmit={handleFormSubmit} className="space-y-4">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="name">Name</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Jane Smith"
                      required
                    />
                  </div>
                  <div>
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="jane@company.com"
                      required
                    />
                  </div>
                </div>

                <div>
                  <Label htmlFor="subject">Subject</Label>
                  <Input
                    id="subject"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                    placeholder="e.g. Can't log in to my account"
                  />
                </div>

                <div>
                  <Label htmlFor="message">Message</Label>
                  <textarea
                    id="message"
                    value={firstMsg}
                    onChange={(e) => setFirstMsg(e.target.value)}
                    placeholder="Describe your issue in detail…"
                    required
                    rows={5}
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm
                               placeholder-slate-400 shadow-sm transition resize-none
                               focus:border-brand-500 focus:outline-none focus:ring-2
                               focus:ring-brand-500/30"
                  />
                </div>

                <button
                  type="submit"
                  disabled={loading}
                  className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold
                             text-white shadow-sm transition hover:bg-brand-700
                             focus:outline-none focus:ring-2 focus:ring-brand-500/50
                             disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {loading ? "Sending…" : "Send message"}
                </button>
              </form>
            </div>
          )}

          {/* ── Chat view (shown after first submission) ── */}
          {started && (
            <div className="bg-white rounded-2xl border border-slate-200 shadow-sm flex flex-col"
                 style={{ minHeight: "520px" }}>

              {/* Chat header */}
              <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
                <div>
                  <p className="text-sm font-semibold text-slate-900">Support conversation</p>
                  <p className="text-xs text-slate-400">{email}</p>
                </div>
                <button
                  onClick={() => {
                    setStarted(false);
                    setMessages([]);
                    setFirstMsg("");
                    setSubject("");
                    setError("");
                  }}
                  className="text-xs text-brand-600 hover:text-brand-700 font-medium transition"
                >
                  New ticket
                </button>
              </div>

              {/* Messages */}
              <div className="flex-1 overflow-y-auto px-5 py-5 space-y-4">
                {messages.map((msg, i) => (
                  <ChatBubble
                    key={i}
                    role={msg.role}
                    text={msg.text}
                    escalated={msg.escalated}
                    ts={msg.ts}
                    isLatest={
                      msg.role === "assistant" &&
                      i === messages.length - 1
                    }
                  />
                ))}
                {loading && <ThinkingBubble />}
                {error && (
                  <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3
                                  text-sm text-red-700">
                    {error}
                  </div>
                )}
                <div ref={bottomRef} />
              </div>

              {/* Follow-up input */}
              <div className="px-5 py-4 border-t border-slate-100">
                <form onSubmit={handleFollowUp} className="flex gap-2">
                  <input
                    type="text"
                    value={followUp}
                    onChange={(e) => setFollowUp(e.target.value)}
                    placeholder="Reply or ask a follow-up question…"
                    disabled={loading}
                    className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm
                               placeholder-slate-400 shadow-sm transition
                               focus:border-brand-500 focus:outline-none focus:ring-2
                               focus:ring-brand-500/30 disabled:bg-slate-100
                               disabled:cursor-not-allowed"
                  />
                  <button
                    type="submit"
                    disabled={loading || !followUp.trim()}
                    className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold
                               text-white shadow-sm transition hover:bg-brand-700
                               focus:outline-none focus:ring-2 focus:ring-brand-500/50
                               disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Send
                  </button>
                </form>
              </div>
            </div>
          )}

        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-slate-400">
        Powered by Flowdesk AI · responses are instant
      </footer>
    </div>
  );
}

/**
 * ChatWidget — floating chat bubble (bottom-right corner).
 * Drop this into any Next.js page to add a support chat overlay.
 *
 * Usage:
 *   import ChatWidget from "../components/ChatWidget";
 *   // Inside your page component:
 *   <ChatWidget />
 */

import { useState, useRef, useEffect } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

// ── Icons ─────────────────────────────────────────────────────────────────────

function IconChat() {
  return (
    <svg className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round"
        d="M8 10h.01M12 10h.01M16 10h.01M21 16a2 2 0 01-2 2H7l-4 4V6a2 2 0 012-2h14a2 2 0 012 2v10z" />
    </svg>
  );
}

function IconClose() {
  return (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function IconSend() {
  return (
    <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
    </svg>
  );
}

// ── Thinking dots ──────────────────────────────────────────────────────────────

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-3 py-2 bg-slate-100 rounded-2xl rounded-tl-sm w-fit">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 rounded-full bg-slate-400 animate-bounce"
          style={{ animationDelay: `${i * 150}ms` }}
        />
      ))}
    </div>
  );
}

// ── Escalation badge ──────────────────────────────────────────────────────────

function EscalatedBadge() {
  return (
    <span className="text-[10px] font-semibold text-amber-700 bg-amber-100 rounded-full px-2 py-0.5 mt-1 inline-block">
      Escalated to human
    </span>
  );
}

// ── Main widget ───────────────────────────────────────────────────────────────

export default function ChatWidget({ customerId = "widget-guest" }) {
  const [open, setOpen]       = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hi! How can I help you today?" },
  ]);
  const [input, setInput]     = useState("");
  const [loading, setLoading] = useState(false);
  const [unread, setUnread]   = useState(0);

  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when widget opens
  useEffect(() => {
    if (open) {
      setUnread(0);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [open]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          channel: "web",
          message: text,
        }),
      });
      const data = await res.json();
      const reply = { role: "assistant", text: data.response, escalated: data.escalated };
      setMessages((prev) => [...prev, reply]);
      if (!open) setUnread((n) => n + 1);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: "Sorry, I couldn't connect to support. Please try again." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  return (
    <>
      {/* ── Popup window ── */}
      {open && (
        <div
          className="fixed bottom-20 right-4 z-50 flex flex-col
                     w-80 sm:w-96 rounded-2xl shadow-2xl border border-slate-200
                     bg-white overflow-hidden"
          style={{ height: "480px" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 bg-brand-600 text-white">
            <div className="flex items-center gap-2">
              <div className="h-8 w-8 rounded-full bg-white/20 flex items-center justify-center font-bold text-sm">
                F
              </div>
              <div>
                <p className="text-sm font-semibold leading-none">Flowdesk Support</p>
                <p className="text-xs text-white/70 mt-0.5">We reply instantly</p>
              </div>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="rounded-lg p-1 hover:bg-white/20 transition"
            >
              <IconClose />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3 bg-slate-50">
            {messages.map((msg, i) => {
              const isUser = msg.role === "user";
              return (
                <div key={i} className={`flex flex-col gap-0.5 ${isUser ? "items-end" : "items-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed
                      ${isUser
                        ? "bg-brand-600 text-white rounded-tr-sm"
                        : "bg-white text-slate-800 border border-slate-200 rounded-tl-sm shadow-sm"
                      }`}
                  >
                    {msg.text}
                  </div>
                  {!isUser && msg.escalated && <EscalatedBadge />}
                </div>
              );
            })}
            {loading && (
              <div className="flex items-start">
                <TypingDots />
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-slate-100 bg-white">
            <div className="flex items-center gap-2">
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type a message…"
                disabled={loading}
                className="flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm
                           placeholder-slate-400 outline-none
                           focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20
                           disabled:bg-slate-50 disabled:cursor-not-allowed transition"
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className="h-9 w-9 flex items-center justify-center rounded-xl
                           bg-brand-600 text-white shadow-sm transition
                           hover:bg-brand-700
                           disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <IconSend />
              </button>
            </div>
            <p className="text-[10px] text-slate-400 text-center mt-2">
              Powered by Flowdesk AI
            </p>
          </div>
        </div>
      )}

      {/* ── Bubble button ── */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-4 right-4 z-50 h-14 w-14 rounded-full
                   bg-brand-600 text-white shadow-lg
                   flex items-center justify-center
                   hover:bg-brand-700 transition-all
                   focus:outline-none focus:ring-4 focus:ring-brand-500/30"
      >
        {open ? <IconClose /> : <IconChat />}
        {!open && unread > 0 && (
          <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-red-500
                           text-white text-[10px] font-bold flex items-center justify-center">
            {unread}
          </span>
        )}
      </button>
    </>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

type Msg = { role: "user" | "assistant"; content: string };

const SUGGESTIONS = [
  "Which teacher needs the most support right now, and why?",
  "How are we tracking toward the school goal by grade?",
  "What key dates are coming up in the next month?",
  "What are my open follow-ups, and which are overdue?",
  "Draft an email to my Grade 3 team about the next data chat.",
];

export default function AssistantPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [aiInfo, setAiInfo] = useState<any>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api
      .me()
      .then((u) => {
        setMe(u);
        // Restore this coach's saved conversation so the AI remembers it.
        api
          .assistantHistory()
          .then((h) => setMsgs(h.messages || []))
          .catch(() => {});
        return api.aiCheck().catch(() => null);
      })
      .then(setAiInfo)
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function clearChat() {
    if (!confirm("Clear the saved conversation and start fresh?")) return;
    try {
      await api.clearAssistant();
      setMsgs([]);
    } catch (err) {
      alert("Could not clear: " + (err as Error).message);
    }
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function send(text: string) {
    if (!text.trim() || busy) return;
    const history = msgs;
    setMsgs([...msgs, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.assistant(text, history);
      setMsgs((m) => [...m, { role: "assistant", content: res.reply }]);
    } catch (err) {
      setMsgs((m) => [
        ...m,
        { role: "assistant", content: "Error: " + (err as Error).message },
      ]);
    } finally {
      setBusy(false);
    }
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const aiReady = aiInfo?.test_call === "ok";

  return (
    <main className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">AI Coach</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="/coach" className="text-sm text-avocado-dark hover:underline">
            ← Planning
          </a>
          {msgs.length > 0 && (
            <button
              onClick={clearChat}
              className="text-sm text-gray-500 hover:text-red-600"
            >
              🗑 Clear chat
            </button>
          )}
          <button
            onClick={() => {
              clearToken();
              router.push("/");
            }}
            className="text-sm text-gray-500 hover:text-gray-800"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex-1 max-w-3xl w-full mx-auto p-6 flex flex-col">
        <h1 className="text-xl font-bold text-gray-800">Expert AI Coach</h1>
        <p className="text-sm text-gray-500 mb-2">
          It knows your live system — goal progress, every teacher&apos;s data,
          pacing, standards &amp; Tier 2 vocabulary, assessments, your notes, and
          key dates — and it <b>remembers your past conversations</b>. Ask a
          question, or have it draft a teacher email.
        </p>
        {aiInfo && !aiReady && (
          <div className="text-xs bg-yellow-50 border border-yellow-200 text-yellow-800 rounded-lg px-3 py-2 mb-3">
            AI status: {aiInfo.test_call}
            {aiInfo.error ? ` — ${aiInfo.error}` : ""}. Responses use a limited
            fallback until the AI key is active on the API service.
          </div>
        )}

        <div className="flex-1 overflow-y-auto space-y-3 py-2">
          {msgs.length === 0 && (
            <div className="space-y-2">
              <p className="text-sm text-gray-500">Try asking:</p>
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="block w-full text-left text-sm bg-white border border-gray-100 rounded-lg px-3 py-2 hover:border-avocado"
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {msgs.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-avocado text-white"
                    : "bg-white border border-gray-100 text-gray-800"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {busy && (
            <div className="text-sm text-gray-400">AI Coach is thinking…</div>
          )}
          <div ref={endRef} />
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
          className="mt-3 flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the AI Coach…"
            className="flex-1 border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-avocado"
          />
          <button
            disabled={busy}
            className="bg-avocado hover:bg-avocado-dark text-white font-semibold rounded-lg px-4 disabled:opacity-60"
          >
            Send
          </button>
        </form>
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

export default function CoachPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [topic, setTopic] = useState<any>(null);
  const [agenda, setAgenda] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api
      .me()
      .then((u) => {
        setMe(u);
        return api.coachDashboard();
      })
      .then(setDash)
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openWeek(id: string) {
    setAgenda(null);
    setTopic(null);
    setBusy(true);
    try {
      setTopic(await api.pacingTopic(id));
    } finally {
      setBusy(false);
    }
  }

  async function makeAgenda(id: string) {
    setBusy(true);
    try {
      const res = await api.generateAgenda(id);
      setAgenda(res.agenda);
    } finally {
      setBusy(false);
    }
  }

  if (!me || !dash) return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">
            {me.name} · <span className="capitalize">{me.role.replace("_", " ")}</span>
          </span>
        </div>
        <button
          onClick={() => {
            clearToken();
            router.push("/");
          }}
          className="text-sm text-gray-500 hover:text-gray-800"
        >
          Sign out
        </button>
      </header>

      <div className="max-w-6xl mx-auto p-6">
        <h1 className="text-xl font-bold text-gray-800 mb-1">
          Collaborative Planning
        </h1>
        <p className="text-sm text-gray-500 mb-5">
          Pacing calendar · {dash.subjects.join(" / ")} · plan the week with your teachers
        </p>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pacing calendar */}
          <div className="md:col-span-1">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">
              Planning Weeks
            </h2>
            <div className="space-y-2">
              {dash.planning_weeks.map((w: any) => (
                <button
                  key={w.id}
                  onClick={() => openWeek(w.id)}
                  className={`w-full text-left bg-white rounded-xl border p-3 transition ${
                    topic?.id === w.id
                      ? "border-avocado ring-1 ring-avocado"
                      : "border-gray-100 hover:border-avocado"
                  }`}
                >
                  <div className="text-xs text-gray-400">
                    Grade {w.grade_level} · {w.subject} · {w.quarter}
                  </div>
                  <div className="font-semibold text-sm text-gray-800">
                    {w.topic_code} · {w.name}
                  </div>
                  <div className="text-xs text-gray-500 mt-1">
                    🎯 {w.learning_target} · {w.benchmark_count} benchmarks
                  </div>
                </button>
              ))}
              {dash.planning_weeks.length === 0 && (
                <p className="text-sm text-gray-400">
                  No pacing topics loaded yet.
                </p>
              )}
            </div>
          </div>

          {/* Selected week + agenda */}
          <div className="md:col-span-2 space-y-4">
            {!topic && (
              <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-400">
                Select a planning week to see the focus and build a PLC agenda.
              </div>
            )}

            {topic && (
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h2 className="font-bold text-gray-800">
                      {topic.topic_code} · {topic.name}
                    </h2>
                    <p className="text-xs text-gray-500">
                      Grade {topic.grade_level} {topic.subject} · {topic.quarter}
                    </p>
                    <p className="text-xs text-gray-400 mt-0.5">{topic.source}</p>
                  </div>
                  <button
                    onClick={() => makeAgenda(topic.id)}
                    disabled={busy}
                    className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60"
                  >
                    {busy ? "Working…" : "Generate PLC Agenda"}
                  </button>
                </div>

                <div className="mt-3 text-sm">
                  <div className="font-semibold text-gray-700">
                    🎯 Learning Target
                  </div>
                  <p className="text-gray-600">{topic.learning_target}</p>
                </div>

                <div className="mt-3 grid sm:grid-cols-2 gap-3 text-sm">
                  <div>
                    <div className="font-semibold text-gray-700 mb-1">
                      I can…
                    </div>
                    <ul className="list-disc ml-4 text-gray-600 space-y-0.5">
                      {topic.success_criteria.map((c: string, i: number) => (
                        <li key={i}>{c}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="font-semibold text-gray-700 mb-1">
                      Vocabulary
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {topic.vocabulary.map((v: string, i: number) => (
                        <span
                          key={i}
                          className="text-xs bg-avocado-light text-avocado-dark rounded-full px-2 py-0.5"
                        >
                          {v}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="mt-4">
                  <div className="font-semibold text-gray-700 text-sm mb-1">
                    Focus Benchmarks
                  </div>
                  <div className="space-y-2">
                    {topic.standards.map((s: any) => (
                      <div
                        key={s.code}
                        className="border border-gray-100 rounded-lg p-2.5"
                      >
                        <div className="text-sm font-medium text-gray-800">
                          {s.code}
                        </div>
                        <p className="text-xs text-gray-600">{s.description}</p>
                        {s.misconceptions && (
                          <p className="text-xs text-red-500 mt-1">
                            ⚠ Common misconception: {s.misconceptions}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {agenda && (
              <div className="bg-white rounded-xl border border-gray-100 p-5">
                <h2 className="font-bold text-gray-800">{agenda.title}</h2>
                <p className="text-xs text-gray-500 mb-3">
                  {agenda.ai_generated
                    ? `AI-generated draft (${agenda.generated_by})`
                    : "Structured template draft"}{" "}
                  · {agenda.week} · review before your meeting
                </p>
                {agenda.sections ? (
                  <div className="space-y-3">
                    {agenda.sections.map((sec: any, i: number) => (
                      <div key={i}>
                        <div className="font-semibold text-sm text-gray-800">
                          {sec.heading}
                        </div>
                        <ul className="list-disc ml-5 text-sm text-gray-600 space-y-0.5">
                          {sec.items.map((it: string, j: number) => (
                            <li key={j}>{it}</li>
                          ))}
                        </ul>
                      </div>
                    ))}
                  </div>
                ) : (
                  <pre className="text-sm whitespace-pre-wrap text-gray-700">
                    {agenda.content}
                  </pre>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

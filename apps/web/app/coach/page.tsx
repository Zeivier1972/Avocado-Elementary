"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

export default function CoachPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [topic, setTopic] = useState<any>(null);
  const [guide, setGuide] = useState<any>(null);
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
    setGuide(null);
    setTopic(null);
    setBusy(true);
    try {
      setTopic(await api.pacingTopic(id));
    } finally {
      setBusy(false);
    }
  }

  async function makeGuide(id: string) {
    setBusy(true);
    try {
      setGuide((await api.generateGuide(id)).guide);
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
        <h1 className="text-xl font-bold text-gray-800 mb-1">Collaborative Planning</h1>
        <p className="text-sm text-gray-500 mb-5">
          Pacing calendar · {dash.subjects.join(" / ")} · plan the week with your teachers
        </p>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pacing calendar */}
          <div className="md:col-span-1">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">Planning Weeks</h2>
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
            </div>
          </div>

          {/* Selected week + guide */}
          <div className="md:col-span-2 space-y-4">
            {!topic && (
              <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-400">
                Select a planning week to see the focus and build a Collaborative
                Planning Guide.
              </div>
            )}

            {topic && <TopicPanel topic={topic} busy={busy} onGuide={() => makeGuide(topic.id)} />}
            {guide && <GuideView guide={guide} />}
          </div>
        </div>
      </div>
    </main>
  );
}

function TopicPanel({ topic, busy, onGuide }: any) {
  const qf = topic.quick_facts || {};
  return (
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
          onClick={onGuide}
          disabled={busy}
          className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60 whitespace-nowrap"
        >
          {busy ? "Working…" : "Generate Planning Guide"}
        </button>
      </div>

      {/* Quick Facts */}
      <div className="mt-3 grid sm:grid-cols-2 gap-x-4 gap-y-1 text-xs bg-gray-50 rounded-lg p-3">
        <Fact label="Time Frame" value={qf.time_frame} />
        <Fact label="ALD Focus" value={qf.ald_focus} />
        <Fact label="Topic Focus" value={qf.topic_focus} />
        <Fact label="Key Benchmarks" value={(qf.key_benchmarks || []).join(", ")} />
        <Fact label="MTR Practices" value={(qf.mtr_practices || []).join(" · ")} />
        <Fact label="Materials" value={(qf.materials || []).join(", ")} />
      </div>

      <div className="mt-3 text-sm">
        <div className="font-semibold text-gray-700">🎯 Learning Goal</div>
        <p className="text-gray-600">{topic.learning_target}</p>
      </div>

      {topic.lessons?.length > 0 && (
        <div className="mt-3 text-sm">
          <div className="font-semibold text-gray-700 mb-1">
            Lesson sequence ({topic.lessons.length})
          </div>
          <ol className="list-decimal ml-5 text-gray-600 space-y-0.5">
            {topic.lessons.map((L: any) => (
              <li key={L.code}>
                <span className="font-medium">{L.code}</span> {L.title}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="font-semibold text-gray-600">{label}: </span>
      <span className="text-gray-500">{value}</span>
    </div>
  );
}

function GuideView({ guide }: any) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5">
      <h2 className="font-bold text-gray-800">{guide.title}</h2>
      <p className="text-xs text-gray-500 mb-3">
        {guide.ai_generated
          ? `AI-generated draft (${guide.generated_by})`
          : "Structured template draft"}{" "}
        — review with your team before teaching.
      </p>

      {/* Topic-level clarifications & misconceptions */}
      {guide.benchmark_clarifications?.length > 0 && (
        <Section title="Benchmark Clarifications">
          {guide.benchmark_clarifications.map((c: any) => (
            <div key={c.code} className="mb-2">
              <div className="text-sm font-medium text-gray-800">{c.code}</div>
              <p className="text-xs text-gray-600">{c.description}</p>
              <ul className="list-disc ml-5 text-xs text-gray-600">
                {(c.clarifications || []).map((x: string, i: number) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {guide.common_misconceptions?.length > 0 && (
        <Section title="Common Misconceptions & Fixes">
          {guide.common_misconceptions.map((m: any, i: number) => (
            <p key={i} className="text-xs text-gray-600 mb-1">
              <span className="font-medium text-red-600">{m.code}: </span>
              {m.note}
            </p>
          ))}
        </Section>
      )}

      {/* Lessons */}
      <div className="mt-4 space-y-3">
        {(guide.lessons || []).map((L: any) => (
          <details
            key={L.code}
            className="border border-gray-100 rounded-lg p-3"
            open
          >
            <summary className="cursor-pointer font-semibold text-gray-800 text-sm">
              Lesson {L.code} — {L.title}
              <span className="text-xs text-gray-400 font-normal">
                {"  "}
                {(L.benchmarks || []).join(", ")}
              </span>
            </summary>
            <div className="mt-2 space-y-2 text-sm">
              <Line label="🎯 Learning Goal" value={L.learning_goal} />
              <List label="Success Criteria" items={L.success_criteria} />
              <Line label="Benchmark Clarification" value={L.benchmark_clarification} />
              {L.misconceptions?.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-700 text-xs">
                    Misconceptions & Fixes
                  </div>
                  {L.misconceptions.map((m: any, i: number) => (
                    <p key={i} className="text-xs text-gray-600">
                      ⚠ {m.misconception}
                      {m.fix ? ` → ${m.fix}` : ""}
                    </p>
                  ))}
                </div>
              )}
              <List label="Teaching Strategy (step-by-step)" items={L.teaching_strategy} ordered />
              {L.cpa && (L.cpa.concrete || L.cpa.pictorial || L.cpa.abstract) && (
                <div className="grid sm:grid-cols-3 gap-2">
                  <CPA label="Concrete" value={L.cpa.concrete} />
                  <CPA label="Pictorial" value={L.cpa.pictorial} />
                  <CPA label="Abstract" value={L.cpa.abstract} />
                </div>
              )}
              <Line label="⭐ Level 3 Proficiency Example" value={L.level3_example} />
              <List label="Checks for Understanding" items={L.cfu} />
              <Line label="You Do (Independent Practice)" value={L.you_do} />
              <Line label="🎫 Exit Ticket" value={L.exit_ticket} highlight />
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function Section({ title, children }: any) {
  return (
    <div className="mt-3 border-t border-gray-50 pt-3">
      <div className="font-semibold text-gray-700 text-sm mb-1">{title}</div>
      {children}
    </div>
  );
}

function Line({ label, value, highlight }: any) {
  if (!value) return null;
  return (
    <div className={highlight ? "bg-avocado-light rounded p-2" : ""}>
      <span className="font-semibold text-gray-700 text-xs">{label}: </span>
      <span className="text-gray-600 text-sm">{value}</span>
    </div>
  );
}

function List({ label, items, ordered }: any) {
  if (!items || items.length === 0) return null;
  const Tag = ordered ? "ol" : "ul";
  return (
    <div>
      <div className="font-semibold text-gray-700 text-xs">{label}</div>
      <Tag
        className={`${
          ordered ? "list-decimal" : "list-disc"
        } ml-5 text-gray-600 text-sm space-y-0.5`}
      >
        {items.map((x: string, i: number) => (
          <li key={i}>{x}</li>
        ))}
      </Tag>
    </div>
  );
}

function CPA({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded p-2">
      <div className="text-xs font-semibold text-avocado-dark">{label}</div>
      <p className="text-xs text-gray-600 whitespace-pre-wrap">{value || "—"}</p>
    </div>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, downloadGuideDocx, getToken } from "@/lib/api";

const GRADES = ["K", "1", "2", "3"];

export default function CoachPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [topic, setTopic] = useState<any>(null);
  const [guide, setGuide] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [grade, setGrade] = useState("3");
  const [summary, setSummary] = useState<any>(null);
  const [rosterMsg, setRosterMsg] = useState("");

  async function loadSummary() {
    try {
      setSummary(await api.schoolSummary());
    } catch {
      /* summary is best-effort */
    }
  }

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
      .then((d) => {
        setDash(d);
        loadSummary();
      })
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onRoster(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setRosterMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.importRoster(form);
      setRosterMsg(
        `Loaded ${r.students_created} new / ${r.students_updated} updated students · ` +
          `${r.teachers_created} teachers · ${r.classes_created} classes` +
          (r.error_count ? ` · ${r.error_count} row error(s)` : "")
      );
      loadSummary();
    } catch (err) {
      setRosterMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

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
        <div className="flex items-center gap-4">
          <a
            href="/goal"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            🎯 Goal
          </a>
          <a
            href="/reports"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            📊 Reports
          </a>
          <a
            href="/assistant"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            🤖 AI Coach
          </a>
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

      <div className="max-w-6xl mx-auto p-6">
        <h1 className="text-xl font-bold text-gray-800 mb-1">Collaborative Planning</h1>
        <p className="text-sm text-gray-500 mb-4">
          Pacing calendar · {dash.subjects.join(" / ")} · plan the week with your teachers
        </p>

        {/* School roster */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 mb-4 flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[200px]">
            <div className="text-sm font-semibold text-gray-700">School Roster</div>
            {summary ? (
              <div className="text-xs text-gray-500">
                {summary.students} students · {summary.teachers} teachers ·{" "}
                {summary.classes} classes
                {summary.by_grade &&
                  Object.keys(summary.by_grade).length > 0 &&
                  " · by grade: " +
                    Object.entries(summary.by_grade)
                      .map(([g, n]) => `${g}=${n}`)
                      .join("  ")}
              </div>
            ) : (
              <div className="text-xs text-gray-400">No roster loaded yet.</div>
            )}
          </div>
          <label className="inline-block bg-gray-800 hover:bg-black text-white text-sm font-semibold rounded-lg px-3 py-2 cursor-pointer">
            {busy ? "Working…" : "Upload Population CSV ⬆"}
            <input type="file" accept=".csv" onChange={onRoster} className="hidden" disabled={busy} />
          </label>
          {rosterMsg && (
            <div className="w-full text-xs text-gray-600">{rosterMsg}</div>
          )}
        </div>

        {/* Grade folders */}
        <div className="flex gap-2 mb-4">
          {GRADES.map((g) => {
            const count = dash.planning_weeks.filter(
              (w: any) => w.grade_level === g
            ).length;
            return (
              <button
                key={g}
                onClick={() => {
                  setGrade(g);
                  setTopic(null);
                  setGuide(null);
                }}
                className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
                  grade === g
                    ? "bg-avocado text-white border-avocado"
                    : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
                }`}
              >
                {g === "K" ? "Kindergarten" : `Grade ${g}`}
                <span className="ml-1 text-xs opacity-70">({count})</span>
              </button>
            );
          })}
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pacing calendar */}
          <div className="md:col-span-1">
            <h2 className="text-sm font-semibold text-gray-700 mb-2">
              {grade === "K" ? "Kindergarten" : `Grade ${grade}`} · Planning Weeks
            </h2>
            <div className="space-y-2">
              {dash.planning_weeks.filter((w: any) => w.grade_level === grade)
                .length === 0 && (
                <div className="text-sm text-gray-400 bg-white border border-dashed border-gray-200 rounded-xl p-4">
                  No pacing guide loaded for this grade yet. Send the pacing guide
                  and it will appear here.
                </div>
              )}
              {dash.planning_weeks
                .filter((w: any) => w.grade_level === grade)
                .map((w: any) => (
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
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-bold text-gray-800">{guide.title}</h2>
        <button
          onClick={() => downloadGuideDocx(guide)}
          className="shrink-0 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg px-3 py-2"
        >
          ⬇ Download Word (.docx)
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-1">
        {guide.ai_generated
          ? `AI-generated draft (${guide.generated_by})`
          : "Structured template draft"}{" "}
        — review with your team before teaching.
      </p>
      {!guide.ai_generated && guide.ai_status && (
        <p className="text-xs bg-yellow-50 border border-yellow-200 text-yellow-800 rounded px-2 py-1 mb-3">
          ⚠ {guide.ai_status}
        </p>
      )}

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
        <Section title="Common Misconceptions">
          <MisconceptionTable rows={guide.common_misconceptions} showCode />
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
              <Line label="Example" value={L.success_example} />
              <Line label="Benchmark Clarification" value={L.benchmark_clarification} />
              <Line label="Example" value={L.benchmark_example} />
              <Line label="Sentence Frame" value={L.sentence_frame} />
              {L.misconceptions?.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-700 text-xs mb-1">
                    Common Misconceptions & Fixes
                  </div>
                  <MisconceptionTable rows={L.misconceptions} />
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
              <Line
                label="🎫 Exit Ticket"
                value={
                  L.exit_ticket && typeof L.exit_ticket === "object"
                    ? `${L.exit_ticket.problem || ""}${
                        L.exit_ticket.answer ? `  →  ${L.exit_ticket.answer}` : ""
                      }`
                    : L.exit_ticket
                }
                highlight
              />
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

function MisconceptionTable({ rows, showCode }: { rows: any[]; showCode?: boolean }) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border border-gray-100">
        <thead>
          <tr className="bg-red-50 text-left text-gray-600">
            {showCode && <th className="p-1 font-semibold">Benchmark</th>}
            <th className="p-1 font-semibold">Misconception</th>
            <th className="p-1 font-semibold">Example Error</th>
            <th className="p-1 font-semibold">Correction Strategy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m, i) => (
            <tr key={i} className="border-t border-gray-100 align-top">
              {showCode && (
                <td className="p-1 font-medium text-red-600 whitespace-nowrap">
                  {m.code}
                </td>
              )}
              <td className="p-1 text-gray-700">{m.misconception}</td>
              <td className="p-1 text-gray-500">{m.example || "—"}</td>
              <td className="p-1 text-gray-700">{m.fix || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

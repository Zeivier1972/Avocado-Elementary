"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, downloadResultsTemplate } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";
import DataSubnav from "@/app/_components/DataSubnav";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

const COLOR_HEX: Record<string, string> = {
  Red: "#C0392B",
  Yellow: "#F1C40F",
  Green: "#27AE60",
  Blue: "#2E86C1",
  Orange: "#E67E22",
};

function Chip({ color, children }: { color?: string; children: any }) {
  const hex = color ? COLOR_HEX[color] : undefined;
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-semibold rounded px-1.5 py-0.5"
      style={
        hex
          ? { backgroundColor: hex + "22", color: hex, border: `1px solid ${hex}55` }
          : { background: "#f3f4f6", color: "#6b7280" }
      }
    >
      {children}
    </span>
  );
}

export default function AssessmentsPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [results, setResults] = useState<any>(null); // {form, analysis}
  const [busy, setBusy] = useState(false);
  const [resBusy, setResBusy] = useState("");
  const [msg, setMsg] = useState("");
  const akRef = useRef<HTMLInputElement>(null);
  const testRef = useRef<HTMLInputElement>(null);

  async function load() {
    setData(await api.getTopicTests());
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api.health().then(setBuild).catch(() => setBuild(null));
    api
      .me()
      .then((u) => {
        setMe(u);
        return load();
      })
      .catch(() => setData({ by_grade: {}, coverage: {} }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onUpload() {
    const ak = akRef.current?.files?.[0];
    if (!ak) {
      setMsg("Choose the answer-key PDF first.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const form = new FormData();
      form.append("answer_key", ak);
      const t = testRef.current?.files?.[0];
      if (t) form.append("test", t);
      const r = await api.importTopicTest(form);
      const f = r.form;
      setMsg(
        `Added ${GRADE_LABEL(f.grade)} ${f.topic_code}: ${f.item_count} items · ` +
          `${f.standards.length} standards${
            r.questions_captured ? ` · ${r.questions_captured} questions captured` : ""
          }.`
      );
      if (akRef.current) akRef.current.value = "";
      if (testRef.current) testRef.current.value = "";
      await load();
    } catch (err) {
      setMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openDetail(id: string) {
    try {
      setDetail(await api.getTopicTest(id));
    } catch (err) {
      alert("Could not open: " + (err as Error).message);
    }
  }

  async function remove(id: string) {
    if (!confirm("Remove this test blueprint?")) return;
    await api.deleteTopicTest(id);
    if (detail?.form?.id === id) setDetail(null);
    if (results?.form?.id === id) setResults(null);
    await load();
  }

  async function openResults(id: string) {
    try {
      setDetail(null);
      setResults(await api.getResults(id));
    } catch (err) {
      alert("Could not load results: " + (err as Error).message);
    }
  }

  async function uploadResults(
    e: React.ChangeEvent<HTMLInputElement>,
    id: string
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    setResBusy(id);
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.importResults(id, form);
      setResults(await api.getResults(id));
      alert(
        `Scored ${r.students} students across ${r.classes.length} classes ` +
          `(${r.questions_matched} questions matched).` +
          (r.linked_to_roster
            ? `\n\n${r.linked_to_roster} students linked to the roster — these ` +
              `topic scores now show in Reports, Goal Analysis, and each ` +
              `teacher's page automatically.`
            : `\n\n(No roster matches yet — upload your student roster so these ` +
              `scores also flow into Reports & Analysis.)`)
      );
    } catch (err) {
      alert("Results upload failed: " + (err as Error).message);
    } finally {
      setResBusy("");
      e.target.value = "";
    }
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const byGrade = data?.by_grade || {};
  const coverage = data?.coverage || {};
  const grades = Object.keys(byGrade);
  const hasData = (data?.total_forms || 0) > 0;

  return (
    <main className="min-h-screen bg-gray-50/60">
      <CoachHeader me={me} active="/assessments" build={build} />
      <div className="max-w-5xl mx-auto p-6 space-y-5">
        <DataSubnav active="/assessments" />
        <div>
          <h1 className="text-xl font-bold text-gray-800">
            Topic Tests & Standards Assessed
          </h1>
          <p className="text-sm text-gray-500">
            Upload each topic test&apos;s <b>answer key</b> (and the test) to record
            which standards it assesses. This is the map we track all year against
            i-Ready and FAST — and the basis for finding the deficient standard per
            class once results come in.
          </p>
        </div>

        {/* Upload */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5">
          <div className="grid sm:grid-cols-2 gap-4">
            <label className="text-sm">
              <span className="font-semibold text-gray-700">
                Answer key (PDF) <span className="text-red-500">*</span>
              </span>
              <input
                ref={akRef}
                type="file"
                accept=".pdf"
                className="mt-1 block w-full text-sm text-gray-600 file:mr-3 file:rounded-lg file:border-0 file:bg-avocado/10 file:px-3 file:py-1.5 file:text-avocado-dark file:font-semibold"
              />
              <span className="text-xs text-gray-400">
                The item / standard / answer table.
              </span>
            </label>
            <label className="text-sm">
              <span className="font-semibold text-gray-700">
                Test (PDF) <span className="text-gray-400">— optional</span>
              </span>
              <input
                ref={testRef}
                type="file"
                accept=".pdf"
                className="mt-1 block w-full text-sm text-gray-600 file:mr-3 file:rounded-lg file:border-0 file:bg-gray-100 file:px-3 file:py-1.5 file:text-gray-600 file:font-semibold"
              />
              <span className="text-xs text-gray-400">
                Captures each question for later DI packets.
              </span>
            </label>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={onUpload}
              disabled={busy}
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-4 py-2 disabled:opacity-60"
            >
              {busy ? "Reading…" : "⬆ Add topic test"}
            </button>
            {msg && <span className="text-sm text-gray-600">{msg}</span>}
          </div>
        </div>

        {!hasData && (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500">
            No topic tests yet. Upload a grade&apos;s topic-test answer key to start
            the standards map.
          </div>
        )}

        {/* Per-grade: standards coverage + the topic tests */}
        {grades.map((g) => (
          <div key={g} className="space-y-3">
            {coverage[g]?.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-5">
                <div className="font-semibold text-gray-800 mb-2">
                  {GRADE_LABEL(g)} — standards we&apos;re tracking
                </div>
                <div className="flex flex-wrap gap-2">
                  {coverage[g].map((c: any) => (
                    <div
                      key={c.standard}
                      title={c.description}
                      className="border border-avocado/30 bg-avocado/5 rounded-lg px-2.5 py-1.5"
                    >
                      <div className="text-sm font-mono font-bold text-avocado-dark">
                        {c.standard}
                      </div>
                      <div className="text-[11px] text-gray-500">
                        {c.items} items · {c.topics.join(", ")}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {byGrade[g].map((f: any) => (
              <div
                key={f.id}
                className="bg-white rounded-2xl border border-gray-100 p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-bold text-gray-800">
                      {GRADE_LABEL(f.grade)} · {f.topic_code}
                    </div>
                    <div className="text-xs text-gray-400 font-mono">
                      {f.test_name || f.test_id}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-gray-500">
                      {f.item_count} items · {f.total_points} pts
                    </span>
                    <button
                      onClick={() => openDetail(f.id)}
                      className="text-sm font-semibold text-avocado-dark hover:underline"
                    >
                      View items
                    </button>
                    <button
                      onClick={() => remove(f.id)}
                      className="text-sm text-gray-400 hover:text-red-600"
                    >
                      Remove
                    </button>
                  </div>
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-3 border-t border-gray-50 pt-3">
                  <span className="text-xs font-semibold text-gray-500">
                    Class results:
                  </span>
                  <label
                    className={`cursor-pointer text-sm font-semibold text-white bg-avocado hover:bg-avocado-dark rounded-lg px-3 py-1.5 ${
                      resBusy === f.id ? "opacity-60 pointer-events-none" : ""
                    }`}
                  >
                    {resBusy === f.id ? "Scoring…" : "⬆ Upload results (Excel)"}
                    <input
                      type="file"
                      accept=".xlsx,.csv"
                      className="hidden"
                      onChange={(e) => uploadResults(e, f.id)}
                    />
                  </label>
                  <button
                    onClick={() =>
                      downloadResultsTemplate(f.id).catch((err) =>
                        alert((err as Error).message)
                      )
                    }
                    className="text-sm font-semibold text-avocado-dark hover:underline"
                  >
                    ⬇ Template
                  </button>
                  <button
                    onClick={() => openResults(f.id)}
                    className="text-sm font-semibold text-avocado-dark hover:underline"
                  >
                    View analysis
                  </button>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {f.by_standard.map((bs: any) => (
                    <span
                      key={bs.standard}
                      className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1"
                    >
                      <span className="font-mono font-semibold text-gray-700">
                        {bs.standard}
                      </span>{" "}
                      <span className="text-gray-500">
                        · {bs.items} items ({bs.points} pts)
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}

        {/* Item detail drawer */}
        {detail && (
          <div className="bg-white rounded-2xl border border-avocado/30 p-5">
            <div className="flex items-center justify-between mb-2">
              <div className="font-bold text-gray-800">
                {GRADE_LABEL(detail.form.grade)} · {detail.form.topic_code} — items
              </div>
              <button
                onClick={() => setDetail(null)}
                className="text-sm text-gray-400 hover:text-gray-700"
              >
                Close ✕
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gray-500 border-b border-gray-100">
                    <th className="p-2 font-semibold">#</th>
                    <th className="p-2 font-semibold">Standard</th>
                    <th className="p-2 font-semibold">Answer</th>
                    <th className="p-2 font-semibold">Pts</th>
                    <th className="p-2 font-semibold">Question</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.items.map((it: any) => (
                    <tr
                      key={it.position}
                      className={`border-b border-gray-50 align-top ${
                        it.scored ? "" : "text-gray-400"
                      }`}
                    >
                      <td className="p-2 font-semibold">{it.position}</td>
                      <td className="p-2 font-mono text-xs">
                        {it.standard || (
                          <span className="text-gray-400">no standard</span>
                        )}
                      </td>
                      <td className="p-2 font-semibold text-avocado-dark">
                        {it.correct_response}
                      </td>
                      <td className="p-2 tabular-nums">{it.points}</td>
                      <td className="p-2 text-gray-600 max-w-md">
                        {it.stem || (
                          <span className="text-gray-300">
                            (upload the test PDF to capture)
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Results analysis */}
        {results && <ResultsPanel data={results} onClose={() => setResults(null)} />}

        {hasData && (
          <p className="text-xs text-gray-400">
            Field-test items with no standard (0 pts) are shown greyed out and don&apos;t
            count. When you upload class results, we&apos;ll score each standard, flag
            the deficient one per class, and pull the most-missed questions into
            DI packets (Red / Yellow / Green) using the ACES model.
          </p>
        )}
      </div>
    </main>
  );
}

function ResultsPanel({ data, onClose }: { data: any; onClose: () => void }) {
  const f = data.form;
  const a = data.analysis;
  const [groups, setGroups] = useState<any[] | null>(null);
  useEffect(() => {
    api
      .diGrouping(f.id)
      .then((r) => setGroups(r.clusters || []))
      .catch(() => setGroups([]));
  }, [f.id]);
  if (!a || a.students === 0) {
    return (
      <div className="bg-white rounded-2xl border border-avocado/30 p-5">
        <div className="flex items-center justify-between">
          <div className="font-bold text-gray-800">
            {GRADE_LABEL(f.grade)} · {f.topic_code} — results
          </div>
          <button
            onClick={onClose}
            className="text-sm text-gray-400 hover:text-gray-700"
          >
            Close ✕
          </button>
        </div>
        <p className="text-sm text-gray-500 mt-2">
          No results uploaded yet. Use “Upload results (Excel)” on this test.
        </p>
      </div>
    );
  }
  return (
    <div className="bg-white rounded-2xl border border-avocado/30 p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-bold text-gray-800">
            {GRADE_LABEL(f.grade)} · {f.topic_code} — results analysis
          </div>
          <div className="text-xs text-gray-500">
            {a.students} students · grade average{" "}
            <Chip color={a.color}>{a.grade_avg}%</Chip>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-sm text-gray-400 hover:text-gray-700"
        >
          Close ✕
        </button>
      </div>

      {/* Standards — which to focus on (grade), ranked by average proficiency */}
      <div>
        <div className="font-semibold text-gray-800 text-sm">
          Benchmarks — least proficient first (pick your DI focus)
        </div>
        <p className="text-xs text-gray-400 mb-2">
          Ranked by <b>proficiency %</b> (points earned ÷ points possible on each
          benchmark) — normalized for the number of questions, so it&apos;s the real
          deficiency, not just raw miss count. The <b>Qs</b> count shows the evidence:
          a low % on few questions is a weaker signal than on many.
        </p>
        <div className="space-y-1.5">
          {a.by_standard.map((s: any, i: number) => (
            <div
              key={s.standard}
              className={`flex items-center gap-3 border rounded-lg px-3 py-2 ${
                i === 0 ? "border-avocado/40 bg-avocado/5" : "border-gray-100"
              }`}
            >
              <span className="text-xs text-gray-400 w-4 tabular-nums">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-mono font-bold text-gray-700">
                  {s.standard}
                  {i === 0 && (
                    <span className="ml-2 text-[10px] font-sans font-semibold text-avocado-dark">
                      ← weakest
                    </span>
                  )}
                </div>
                {s.description && (
                  <div className="text-xs text-gray-500 truncate" title={s.description}>
                    {s.description}
                  </div>
                )}
              </div>
              {typeof s.questions === "number" && (
                <span
                  className={`text-[11px] whitespace-nowrap ${
                    s.questions <= 1 ? "text-amber-600 font-semibold" : "text-gray-400"
                  }`}
                  title={
                    s.questions <= 1
                      ? "Only 1 question — thin evidence; confirm with i-Ready/FAST before heavy reteach."
                      : `${s.questions} questions assess this standard`
                  }
                >
                  {s.questions} Q{s.questions === 1 ? "" : "s"}
                  {s.questions <= 1 ? " ⚠" : ""}
                </span>
              )}
              <Chip color={s.color}>{s.percent}%</Chip>
              <a
                href={`/di-focus?grade=${f.grade}&standard=${encodeURIComponent(
                  s.standard
                )}&form_id=${f.id}`}
                className="text-xs font-semibold text-white bg-avocado hover:bg-avocado-dark rounded-lg px-2.5 py-1 whitespace-nowrap"
              >
                Plan DI →
              </a>
            </div>
          ))}
        </div>
      </div>

      {/* DI grouping recommendation — who can share one packet */}
      {groups && groups.length > 0 && (
        <div className="bg-avocado/5 border border-avocado/30 rounded-xl p-4">
          <div className="font-semibold text-gray-800 text-sm">
            🧩 DI grouping — who can share one packet
          </div>
          <p className="text-xs text-gray-500 mb-2">
            Based on what each class actually missed. <b>Default to per-class</b> for
            accuracy — each class&apos;s deficiency is measured on its own students.
            Share <b>one</b> packet only where classes truly overlap (the SHARE rows
            below). {groups.length === 1 && groups[0].shared
              ? "Here every class shares the same gap — a single grade-wide packet works."
              : "Give the OWN-PACKET classes their own."}
          </p>
          <div className="space-y-2">
            {groups.map((g: any, i: number) => (
              <div
                key={i}
                className={`flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 border ${
                  g.shared ? "border-avocado/40 bg-white" : "border-gray-100 bg-white"
                }`}
              >
                {(() => {
                  const badge: Record<string, [string, string]> = {
                    share: [`SHARE · ${g.class_count} classes`, "bg-avocado text-white"],
                    own: ["OWN PACKET", "bg-gray-100 text-gray-600"],
                    enrichment: ["ENRICHMENT · proficient", "bg-blue-100 text-blue-700"],
                    unmatched: ["FIX ROSTER", "bg-amber-100 text-amber-800"],
                  };
                  const [label, cls] = badge[g.kind] || badge.own;
                  return (
                    <span className={`text-[10px] font-bold rounded px-2 py-0.5 ${cls}`}>
                      {label}
                    </span>
                  );
                })()}
                <span className="text-sm text-gray-800 font-semibold">
                  {g.teachers.join(", ")}
                </span>
                {g.standard && (
                  <span className="text-xs font-mono text-gray-500">{g.standard}</span>
                )}
                {g.shared_questions?.length > 0 && (
                  <span className="text-xs text-gray-400">
                    · missed {g.shared_questions.join(", ")}
                  </span>
                )}
                {(g.kind === "share" || g.kind === "own") &&
                  (g.red > 0 || g.yellow > 0) && (
                    <span className="text-xs font-semibold">
                      · <span className="text-red-600">{g.red} Red</span>{" "}
                      <span className="text-amber-600">{g.yellow} Yellow</span> to
                      reteach
                    </span>
                  )}
                {g.kind === "enrichment" ? (
                  <span className="ml-auto text-xs text-blue-700">
                    No reteach — give enrichment / Dig Deeper
                  </span>
                ) : g.kind === "unmatched" ? (
                  <span className="ml-auto text-xs text-amber-700">
                    {g.students} students didn&apos;t match the roster — re-check names/IDs
                  </span>
                ) : (
                  <a
                    href={`/di-focus?grade=${f.grade}&standard=${encodeURIComponent(
                      g.standard
                    )}&form_id=${f.id}&teacher=${encodeURIComponent(
                      g.teachers.join(",")
                    )}`}
                    className="ml-auto text-xs font-semibold text-white bg-avocado hover:bg-avocado-dark rounded-lg px-2.5 py-1 whitespace-nowrap"
                  >
                    {g.shared ? "Plan 1 packet for group →" : "Plan DI →"}
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Per class */}
      <div>
        <div className="font-semibold text-gray-800 text-sm mb-1">By class</div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="p-2 font-semibold">Class</th>
                <th className="p-2 font-semibold">Students</th>
                <th className="p-2 font-semibold">Average</th>
                <th className="p-2 font-semibold">DI target (evidence-backed)</th>
                <th className="p-2 font-semibold">Most-missed Qs</th>
              </tr>
            </thead>
            <tbody>
              {a.classes.map((c: any) => (
                <tr key={c.teacher} className="border-b border-gray-50 align-top">
                  <td className="p-2 font-semibold text-gray-800">{c.teacher}</td>
                  <td className="p-2 text-gray-500">{c.students}</td>
                  <td className="p-2">
                    <Chip color={c.color}>{c.avg_percent}%</Chip>
                  </td>
                  <td className="p-2">
                    {c.needs_di ? (
                      <span className="font-mono text-xs">
                        {c.di_target}{" "}
                        {typeof c.di_target_pct === "number" && (
                          <span className="text-gray-500">{c.di_target_pct}%</span>
                        )}{" "}
                        <a
                          href={`/di-focus?grade=${f.grade}&standard=${encodeURIComponent(
                            c.di_target
                          )}&form_id=${f.id}&teacher=${encodeURIComponent(c.teacher)}`}
                          className="text-avocado-dark font-semibold hover:underline font-sans"
                        >
                          → DI for this class
                        </a>
                        <div className="text-[11px] font-sans mt-0.5">
                          <span className="text-red-600 font-semibold">
                            🔴 {c.red_on_target} Red
                          </span>{" "}
                          <span className="text-amber-600 font-semibold">
                            🟡 {c.yellow_on_target} Yellow
                          </span>{" "}
                          <span className="text-green-700 font-semibold">
                            🟢 {c.green_on_target} Green
                          </span>
                        </div>
                      </span>
                    ) : (
                      <span className="text-xs text-green-700 font-semibold">
                        ✓ All Green — enrichment
                      </span>
                    )}
                    {c.di_note && c.needs_di && (
                      <div className="text-[11px] text-amber-600 font-sans mt-0.5">
                        ⚠ {c.di_note}
                      </div>
                    )}
                  </td>
                  <td className="p-2 text-gray-600">
                    {c.most_missed
                      .map((m: any) => `Q${m.position} (${m.miss_pct}%)`)
                      .join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Most-missed questions (grade) */}
      <div>
        <div className="font-semibold text-gray-800 text-sm mb-1">
          Most-missed questions (grade) — DI packet candidates
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="p-2 font-semibold">Q</th>
                <th className="p-2 font-semibold">Standard</th>
                <th className="p-2 font-semibold">Answer</th>
                <th className="p-2 font-semibold">% missed</th>
                <th className="p-2 font-semibold">Question</th>
              </tr>
            </thead>
            <tbody>
              {a.most_missed.map((m: any) => (
                <tr key={m.position} className="border-b border-gray-50 align-top">
                  <td className="p-2 font-semibold">{m.position}</td>
                  <td className="p-2 font-mono text-xs">{m.standard}</td>
                  <td className="p-2 font-semibold text-avocado-dark">
                    {m.correct_response}
                  </td>
                  <td className="p-2">
                    <Chip color={m.miss_pct >= 50 ? "Red" : m.miss_pct >= 30 ? "Yellow" : "Green"}>
                      {m.miss_pct}%
                    </Chip>
                  </td>
                  <td className="p-2 text-gray-600 max-w-sm">
                    {m.stem || (
                      <span className="text-gray-300">
                        (upload the test PDF to show)
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Per student */}
      <details>
        <summary className="cursor-pointer text-sm font-semibold text-avocado-dark">
          Per-student scores ({a.students_list.length})
        </summary>
        <div className="overflow-x-auto mt-2">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-100">
                <th className="p-2 font-semibold">Student</th>
                <th className="p-2 font-semibold">Class</th>
                <th className="p-2 font-semibold">Score</th>
                <th className="p-2 font-semibold">Missed Qs</th>
              </tr>
            </thead>
            <tbody>
              {a.students_list.map((s: any, i: number) => (
                <tr key={i} className="border-b border-gray-50">
                  <td className="p-2 text-gray-800">
                    {s.student_name}
                    {s.student_id && (
                      <span className="text-gray-400 text-xs"> · {s.student_id}</span>
                    )}
                  </td>
                  <td className="p-2 text-gray-500">{s.teacher}</td>
                  <td className="p-2">
                    <Chip color={s.color}>{s.percent}%</Chip>
                  </td>
                  <td className="p-2 text-gray-500 text-xs">
                    {(s.missed || []).map((q: number) => `Q${q}`).join(", ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

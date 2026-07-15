"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

const GRADES = ["K", "1", "2", "3"];
const PM = ["PM1", "PM2", "PM3"];

export default function ReportsPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [grade, setGrade] = useState("3");
  const [report, setReport] = useState<any>(null);
  const [fast, setFast] = useState<any>(null);
  const [period, setPeriod] = useState("PM1");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [mode, setMode] = useState<"grade" | "teacher">("grade");
  const [teacherList, setTeacherList] = useState<any[]>([]);
  const [teacherRep, setTeacherRep] = useState<any>(null);

  async function loadTeachers() {
    try {
      const r = await api.teachers();
      setTeacherList(r.teachers || []);
    } catch {
      /* ignore */
    }
  }

  async function openTeacher(id: string) {
    setTeacherRep(null);
    try {
      setTeacherRep(await api.teacherReport(id));
    } catch {
      /* ignore */
    }
  }

  async function load(g: string, p = period) {
    setReport(null);
    setFast(null);
    try {
      const [rep, fa] = await Promise.all([
        api.gradeReport(g),
        api.fastAnalysis(g, "MATH", p).catch(() => null),
      ]);
      setReport(rep);
      setFast(fa);
    } catch {
      /* ignore */
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
        return load(grade);
      })
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.importExcel(form);
      setMsg(
        `Imported: ${r.students_created} new / ${r.students_updated} updated students · ` +
          `${r.assessments_created + r.assessments_updated} assessments`
      );
      await load(grade);
    } catch (err) {
      setMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">Data &amp; Reports</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="/coach" className="text-sm text-avocado-dark hover:underline">
            Planning
          </a>
          <a href="/assistant" className="text-sm text-avocado-dark hover:underline">
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
        {/* Import area */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 mb-4 flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[220px]">
            <div className="text-sm font-semibold text-gray-700">
              Import assessment data
            </div>
            <div className="text-xs text-gray-500">
              Upload the Class Lists first (sets grades), then the Math Topic
              Tracker. FAST PM1/2/3, iReady AP1/2, and Topic assessments load
              automatically.
            </div>
          </div>
          <label className="inline-block bg-gray-800 hover:bg-black text-white text-sm font-semibold rounded-lg px-3 py-2 cursor-pointer">
            {busy ? "Importing…" : "Upload Excel (.xlsx) ⬆"}
            <input
              type="file"
              accept=".xlsx"
              onChange={onImport}
              className="hidden"
              disabled={busy}
            />
          </label>
          {msg && <div className="w-full text-xs text-gray-600">{msg}</div>}
        </div>

        {/* View mode toggle */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setMode("grade")}
            className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
              mode === "grade"
                ? "bg-avocado-dark text-white border-avocado-dark"
                : "bg-white text-gray-600 border-gray-200"
            }`}
          >
            By Grade
          </button>
          <button
            onClick={() => {
              setMode("teacher");
              if (teacherList.length === 0) loadTeachers();
            }}
            className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
              mode === "teacher"
                ? "bg-avocado-dark text-white border-avocado-dark"
                : "bg-white text-gray-600 border-gray-200"
            }`}
          >
            By Teacher
          </button>
        </div>

        {mode === "teacher" && (
          <TeacherView
            teachers={teacherList}
            report={teacherRep}
            onOpen={openTeacher}
          />
        )}

        {/* Grade tabs */}
        {mode === "grade" && (
        <>
        <div className="flex gap-2 mb-4">
          {GRADES.map((g) => (
            <button
              key={g}
              onClick={() => {
                setGrade(g);
                load(g);
              }}
              className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
                grade === g
                  ? "bg-avocado text-white border-avocado"
                  : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
              }`}
            >
              {g === "K" ? "Kindergarten" : `Grade ${g}`}
            </button>
          ))}
        </div>

        {/* FAST item analysis */}
        {fast && fast.has_data && (
          <div className="mb-6">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-lg font-bold text-gray-800">
                FAST Math Item Analysis
              </h2>
              <div className="flex gap-1">
                {["PM1", "PM2", "PM3"].map((p) => (
                  <button
                    key={p}
                    onClick={() => {
                      setPeriod(p);
                      load(grade, p);
                    }}
                    className={`px-3 py-1 rounded text-sm font-semibold border ${
                      period === p
                        ? "bg-avocado text-white border-avocado"
                        : "bg-white text-gray-600 border-gray-200"
                    }`}
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <FastAnalysis fast={fast} />
          </div>
        )}

        {!report && <div className="text-gray-400">Loading report…</div>}

        {report && (
          <div className="space-y-4">
            <div className="text-sm text-gray-500">
              {report.students} students in{" "}
              {grade === "K" ? "Kindergarten" : `Grade ${grade}`}
            </div>

            <div className="grid md:grid-cols-2 gap-4">
              <ProficiencyCard title="FAST Math — % Proficient (Level 3+)" data={report.fast_math} />
              <ProficiencyCard title="FAST ELA — % Proficient (Level 3+)" data={report.fast_ela} />
            </div>

            {Object.keys(report.topic_assessments || {}).length > 0 && (
              <Card title="Math Topic Assessments — class average %">
                <div className="flex flex-wrap gap-2">
                  {Object.entries(report.topic_assessments).map(
                    ([tp, v]: any) => (
                      <div
                        key={tp}
                        className="border border-gray-100 rounded-lg px-3 py-2 text-center min-w-[70px]"
                      >
                        <div className="text-xs text-gray-500">
                          {tp.replace("TP", "Topic ")}
                        </div>
                        <div
                          className={`text-lg font-bold ${
                            v.avg_pct >= 70
                              ? "text-green-600"
                              : v.avg_pct >= 60
                              ? "text-yellow-600"
                              : "text-red-600"
                          }`}
                        >
                          {v.avg_pct}%
                        </div>
                      </div>
                    )
                  )}
                </div>
              </Card>
            )}

            <Card
              title={`Watchlist — students below proficiency (${report.watchlist_count})`}
            >
              {report.watchlist.length === 0 ? (
                <p className="text-sm text-gray-400">
                  No assessment data yet for this grade.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                        <th className="py-1">Student</th>
                        <th className="py-1">FAST Math Level</th>
                        <th className="py-1">Topic Avg</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.watchlist.map((s: any) => (
                        <tr key={s.student_id} className="border-b border-gray-50">
                          <td className="py-1">{s.name}</td>
                          <td className="py-1">
                            {s.fast_math_level != null ? (
                              <span
                                className={
                                  s.fast_math_level < 3
                                    ? "text-red-600 font-semibold"
                                    : ""
                                }
                              >
                                {s.fast_math_level}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="py-1">
                            {s.topic_avg != null ? `${s.topic_avg}%` : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}
        </>
        )}
      </div>
    </main>
  );
}

function TeacherView({
  teachers,
  report,
  onOpen,
}: {
  teachers: any[];
  report: any;
  onOpen: (id: string) => void;
}) {
  return (
    <div className="space-y-4">
      <Card title="Teachers">
        {teachers.length === 0 ? (
          <p className="text-sm text-gray-400">
            No teachers linked yet. Upload the Class Lists (or student roster CSV)
            to establish teacher rosters.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <th className="py-1">Teacher</th>
                  <th className="py-1">Grade</th>
                  <th className="py-1">Students</th>
                  <th className="py-1">FAST Math % L3+</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {teachers.map((t) => (
                  <tr key={t.teacher_id} className="border-b border-gray-50">
                    <td className="py-1 font-medium">{t.name}</td>
                    <td className="py-1 text-gray-500">
                      {t.grades.filter(Boolean).join(", ")}
                    </td>
                    <td className="py-1">{t.students}</td>
                    <td className="py-1">
                      {t.pct_level_3_plus != null ? (
                        <span
                          className={
                            t.pct_level_3_plus >= 50
                              ? "text-green-600 font-semibold"
                              : "text-red-600 font-semibold"
                          }
                        >
                          {t.pct_level_3_plus}%
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="py-1 text-right">
                      <button
                        onClick={() => onOpen(t.teacher_id)}
                        className="text-avocado-dark font-semibold hover:underline"
                      >
                        View roster →
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {report && (
        <Card
          title={`${report.teacher} — ${report.students} students · ${report.pct_level_3_plus}% Level 3+`}
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-gray-500 border-b border-gray-100">
                  <th className="py-1">Student</th>
                  <th className="py-1 text-center">PM1</th>
                  <th className="py-1 text-center">PM2</th>
                  <th className="py-1 text-center">PM3</th>
                  <th className="py-1 text-center">AP1</th>
                  <th className="py-1 text-center">AP2</th>
                  <th className="py-1 text-center">Topic Avg</th>
                  <th className="py-1 text-center">On Track</th>
                </tr>
              </thead>
              <tbody>
                {report.roster.map((r: any) => (
                  <tr key={r.student_id} className="border-b border-gray-50">
                    <td className="py-1">
                      {r.name}
                      {r.flags?.ell && (
                        <span className="ml-1 text-[10px] text-blue-500">ELL</span>
                      )}
                      {r.flags?.ese && (
                        <span className="ml-1 text-[10px] text-purple-500">ESE</span>
                      )}
                    </td>
                    <Lvl v={r.fast_pm1} />
                    <Lvl v={r.fast_pm2} />
                    <Lvl v={r.fast_pm3} />
                    <td className="py-1 text-center text-gray-600">
                      {r.iready_ap1 ?? "—"}
                    </td>
                    <td className="py-1 text-center text-gray-600">
                      {r.iready_ap2 ?? "—"}
                    </td>
                    <td className="py-1 text-center">
                      {r.topic_avg != null ? `${r.topic_avg}%` : "—"}
                    </td>
                    <td className="py-1 text-center">
                      {r.on_track ? "✅" : "🔴"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

function Lvl({ v }: { v: any }) {
  const isLevel = typeof v === "number" && v >= 1 && v <= 5;
  return (
    <td className="py-1 text-center">
      {v == null ? (
        <span className="text-gray-300">—</span>
      ) : (
        <span
          className={
            isLevel
              ? v >= 3
                ? "text-green-600 font-semibold"
                : "text-red-600 font-semibold"
              : "text-gray-600"
          }
        >
          {v}
        </span>
      )}
    </td>
  );
}

function FastAnalysis({ fast }: { fast: any }) {
  const o = fast.overall;
  const dist = o.level_distribution || {};
  const maxD = Math.max(1, ...Object.values(dist).map((n: any) => n));
  return (
    <div className="space-y-4">
      {/* Overall */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5 grid md:grid-cols-4 gap-4">
        <div>
          <div className="text-xs text-gray-500">% Level 3+ ({fast.period})</div>
          <div
            className={`text-4xl font-bold ${
              o.pct_level_3_plus >= 50 ? "text-green-600" : "text-red-600"
            }`}
          >
            {o.pct_level_3_plus}%
          </div>
          <div className="text-xs text-gray-400">Goal: all L3+ by PM3</div>
        </div>
        <div className="md:col-span-2">
          <div className="text-xs text-gray-500 mb-1">
            Achievement level distribution ({o.students_tested} tested)
          </div>
          <div className="flex items-end gap-2 h-20">
            {["1", "2", "3", "4", "5"].map((lv) => (
              <div key={lv} className="flex-1 text-center">
                <div className="h-14 flex items-end justify-center">
                  <div
                    className={`w-full rounded-t ${
                      Number(lv) >= 3 ? "bg-green-500" : "bg-red-400"
                    }`}
                    style={{ height: `${((dist[lv] || 0) / maxD) * 100}%` }}
                  />
                </div>
                <div className="text-xs font-semibold">{dist[lv] || 0}</div>
                <div className="text-[10px] text-gray-400">L{lv}</div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-500">Overall % correct</div>
          <div className="text-2xl font-bold text-gray-800">
            {o.overall_pct_correct}%
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Avg scale {o.avg_scale_score}
          </div>
        </div>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        {/* By domain */}
        <Card title="Performance by Domain">
          <div className="space-y-2">
            {fast.by_domain.map((d: any) => (
              <div key={d.domain}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-gray-700">{d.domain}</span>
                  <span className="font-semibold">{d.pct}%</span>
                </div>
                <div className="h-2 bg-gray-100 rounded">
                  <div
                    className={`h-2 rounded ${
                      d.pct >= 60 ? "bg-green-500" : d.pct >= 40 ? "bg-yellow-500" : "bg-red-500"
                    }`}
                    style={{ width: `${d.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* Focus standards */}
        <Card title="Focus Standards (lowest benchmarks)">
          <div className="space-y-1.5">
            {fast.focus_standards.map((b: any) => (
              <div key={b.benchmark} className="flex items-start gap-2 text-sm">
                <span className="text-red-600 font-bold w-10">{b.pct}%</span>
                <div>
                  <span className="font-medium">{b.benchmark}</span>
                  {b.description && (
                    <span className="text-gray-500 text-xs"> — {b.description}</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Target students */}
      <div className="grid md:grid-cols-2 gap-4">
        <Card title="🎯 Bubble — Level 2 closest to Level 3">
          <TargetList rows={fast.target_students.bubble_level2} showScale />
        </Card>
        <Card title="Lowest — Level 1 needing intensive support">
          <TargetList rows={fast.target_students.lowest_level1} />
        </Card>
      </div>
    </div>
  );
}

function TargetList({ rows, showScale }: { rows: any[]; showScale?: boolean }) {
  if (!rows || rows.length === 0)
    return <p className="text-sm text-gray-400">None.</p>;
  return (
    <table className="w-full text-sm">
      <tbody>
        {rows.map((s: any) => (
          <tr key={s.student_id} className="border-b border-gray-50">
            <td className="py-1">{s.name}</td>
            <td className="py-1 text-right text-gray-500">{s.percent_score}%</td>
            {showScale && (
              <td className="py-1 text-right text-gray-400 text-xs">
                {s.scale_score}
              </td>
            )}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProficiencyCard({ title, data }: { title: string; data: any }) {
  const periods = PM.filter((p) => data && data[p]);
  return (
    <Card title={title}>
      {periods.length === 0 ? (
        <p className="text-sm text-gray-400">No FAST data yet.</p>
      ) : (
        <div className="flex items-end gap-4">
          {periods.map((p) => {
            const d = data[p];
            const color =
              d.pct_proficient >= 60
                ? "bg-green-500"
                : d.pct_proficient >= 40
                ? "bg-yellow-500"
                : "bg-red-500";
            return (
              <div key={p} className="flex-1 text-center">
                <div className="h-28 flex items-end justify-center">
                  <div
                    className={`${color} w-10 rounded-t`}
                    style={{ height: `${Math.max(4, d.pct_proficient)}%` }}
                    title={`${d.proficient}/${d.n}`}
                  />
                </div>
                <div className="text-lg font-bold text-gray-800">
                  {d.pct_proficient}%
                </div>
                <div className="text-xs text-gray-500">{p}</div>
                <div className="text-[10px] text-gray-400">n={d.n}</div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">{title}</h2>
      {children}
    </div>
  );
}

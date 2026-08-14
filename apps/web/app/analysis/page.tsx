"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, downloadGoalAnalysisXlsx } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADES = ["K", "1", "2", "3", "4"];
const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);
const LEVEL_COLORS: Record<number, { name: string; hex: string; dark: boolean }> = {
  1: { name: "Red", hex: "#C0392B", dark: true },
  2: { name: "Yellow", hex: "#F1C40F", dark: false },
  3: { name: "Green", hex: "#27AE60", dark: true },
  4: { name: "Blue", hex: "#2E86C1", dark: true },
  5: { name: "Orange", hex: "#E67E22", dark: true },
};

const STATUS: Record<string, { label: string; cls: string }> = {
  above: { label: "Above goal", cls: "bg-green-50 text-green-700 border-green-200" },
  meeting: { label: "Meeting", cls: "bg-green-50 text-green-700 border-green-200" },
  below: { label: "Below goal", cls: "bg-red-50 text-red-700 border-red-200" },
  no_topic: { label: "No topic data", cls: "bg-gray-100 text-gray-500 border-gray-200" },
  no_fast: { label: "No FAST", cls: "bg-gray-100 text-gray-500 border-gray-200" },
};

function goalText(m: number | null, x: number | null) {
  if (m == null) return "—";
  return m === x ? `${m}%` : `${m}–${x}%`;
}

export default function AnalysisPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [grade, setGrade] = useState("3");
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api.health().then(setBuild).catch(() => setBuild(null));
    api.me().then(setMe).catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!me) return;
    setLoading(true);
    api
      .goalAnalysis(grade)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [me, grade]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const s = data?.summary;
  const students = data?.students || [];
  const coverage = data?.benchmark_coverage || [];

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/analysis" build={build} />
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Goal Analysis</h1>
          <p className="text-gray-500 text-sm max-w-3xl">
            Each student's <b>FAST-based topic goal</b> (from the Math Goal Setting
            Rubric) next to their <b>actual topic-assessment average</b> — who's
            meeting the mark their FAST score sets, and who's projected to reach
            the school goal (Level 3+). Grows as you upload FAST, i-Ready, and
            topic reports.
          </p>
        </div>

        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex gap-2 flex-wrap">
            {GRADES.map((g) => (
              <button
                key={g}
                onClick={() => setGrade(g)}
                className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
                  grade === g
                    ? "bg-avocado text-white border-avocado"
                    : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
                }`}
              >
                {GRADE_LABEL(g)}
              </button>
            ))}
          </div>
          {data?.has_fast && (
            <button
              onClick={() =>
                downloadGoalAnalysisXlsx(grade).catch((e) =>
                  alert("Download failed: " + (e as Error).message)
                )
              }
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2"
            >
              ⬇ Download Excel (color-coded)
            </button>
          )}
        </div>

        {/* Color legend */}
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="text-gray-500">Topic color code:</span>
          {[1, 2, 3, 4, 5].map((l) => (
            <span
              key={l}
              className="rounded px-2 py-0.5 font-semibold"
              style={{
                backgroundColor: LEVEL_COLORS[l].hex,
                color: LEVEL_COLORS[l].dark ? "#fff" : "#000",
              }}
            >
              L{l} {LEVEL_COLORS[l].name}
            </span>
          ))}
        </div>

        {loading ? (
          <div className="text-gray-400 text-sm p-6">Analyzing…</div>
        ) : !data?.has_fast ? (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500 text-sm">
            No FAST scale scores for {GRADE_LABEL(grade)} yet. Upload the FAST and
            topic-assessment reports and this fills in — comparing each student's
            topic average to their FAST-based goal and projecting end-of-year.
          </div>
        ) : (
          <>
            {/* Summary */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {[
                ["With FAST", s.with_fast, "text-gray-800"],
                ["Meeting/above goal", s.meeting + s.above, "text-green-700"],
                ["Below goal", s.below, "text-red-600"],
                ["Projected Level 3+", s.projected_goal, "text-avocado-dark"],
                ["Students", s.students, "text-gray-800"],
              ].map(([label, n, cls]) => (
                <div
                  key={label as string}
                  className="bg-white rounded-xl border border-gray-100 p-3 text-center"
                >
                  <div className={`text-2xl font-bold tabular-nums ${cls}`}>{n as number}</div>
                  <div className="text-[11px] text-gray-500">{label}</div>
                </div>
              ))}
            </div>

            {/* Students */}
            <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden">
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 font-semibold text-gray-800 text-sm">
                FAST ↔ Topic goal — {GRADE_LABEL(grade)}
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs min-w-[820px]">
                  <thead>
                    <tr className="text-left text-gray-500 border-b border-gray-100">
                      <th className="p-2 font-semibold">Student</th>
                      <th className="p-2 font-semibold">FAST scale</th>
                      <th className="p-2 font-semibold">Level</th>
                      <th className="p-2 font-semibold">Instructional level</th>
                      <th className="p-2 font-semibold">Topic goal</th>
                      <th className="p-2 font-semibold">Topic avg</th>
                      <th className="p-2 font-semibold">Status</th>
                      <th className="p-2 font-semibold">Trend</th>
                      <th className="p-2 font-semibold">EOY projection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {students.map((r: any) => {
                      const st = STATUS[r.status] || STATUS.no_fast;
                      return (
                        <tr
                          key={r.student_id}
                          className="border-b border-gray-50 align-top"
                        >
                          <td className="p-2 text-gray-800 whitespace-nowrap">{r.name}</td>
                          <td className="p-2 tabular-nums text-gray-700">
                            {r.fast_scale ?? "—"}
                          </td>
                          <td className="p-2">
                            {r.fast_level ? (
                              <span
                                className={
                                  r.fast_level >= 3
                                    ? "text-green-700 font-semibold"
                                    : "text-red-600"
                                }
                              >
                                {r.fast_level}
                              </span>
                            ) : (
                              "—"
                            )}
                          </td>
                          <td className="p-2 text-gray-600">{r.instructional || "—"}</td>
                          <td className="p-2 tabular-nums text-gray-700">
                            {goalText(r.goal_min, r.goal_max)}
                          </td>
                          <td className="p-2 tabular-nums">
                            {r.topic_avg != null ? (
                              <span
                                className="inline-block rounded px-1.5 py-0.5 font-semibold"
                                title={
                                  r.topic_level
                                    ? `Level ${r.topic_level} (${LEVEL_COLORS[r.topic_level]?.name})`
                                    : ""
                                }
                                style={
                                  r.topic_level
                                    ? {
                                        backgroundColor:
                                          LEVEL_COLORS[r.topic_level].hex,
                                        color: LEVEL_COLORS[r.topic_level].dark
                                          ? "#fff"
                                          : "#000",
                                      }
                                    : {}
                                }
                              >
                                {r.topic_avg}%
                              </span>
                            ) : (
                              <span className="text-gray-400">—</span>
                            )}
                            {r.gap != null && (
                              <span
                                className={
                                  r.gap >= 0
                                    ? "text-green-600 ml-1"
                                    : "text-red-600 ml-1"
                                }
                              >
                                ({r.gap >= 0 ? "+" : ""}
                                {r.gap})
                              </span>
                            )}
                          </td>
                          <td className="p-2">
                            <span
                              className={`text-[10px] font-semibold border rounded px-1.5 py-0.5 ${st.cls}`}
                            >
                              {st.label}
                            </span>
                          </td>
                          <td className="p-2 text-gray-500">
                            {r.trend === "up" ? "↑" : r.trend === "down" ? "↓" : "→"}
                          </td>
                          <td className="p-2">
                            {r.projected === true ? (
                              <span className="text-green-700">On track ✓</span>
                            ) : r.projected === false ? (
                              <span className="text-red-600">At risk</span>
                            ) : (
                              <span className="text-gray-400">—</span>
                            )}
                            <div className="text-[10px] text-gray-400">
                              {r.projection_note}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Benchmark coverage */}
            {coverage.length > 0 && (
              <div className="bg-white rounded-2xl border border-gray-100 p-4">
                <div className="font-semibold text-gray-800 mb-1">
                  Benchmark coverage &amp; deficiencies
                </div>
                <p className="text-xs text-gray-400 mb-2">
                  What's been assessed (from FAST items), how many times, how many
                  questions, and average performance — weakest first.
                </p>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border border-gray-100">
                    <thead>
                      <tr className="bg-gray-50 text-left text-gray-500">
                        <th className="p-1.5 font-semibold">Benchmark</th>
                        <th className="p-1.5 font-semibold">Description</th>
                        <th className="p-1.5 font-semibold">Times assessed</th>
                        <th className="p-1.5 font-semibold">Questions</th>
                        <th className="p-1.5 font-semibold">Avg %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {coverage.map((c: any) => (
                        <tr key={c.benchmark} className="border-t border-gray-100 align-top">
                          <td className="p-1.5 font-medium text-gray-700 whitespace-nowrap">
                            {c.benchmark}
                          </td>
                          <td className="p-1.5 text-gray-600">{c.description}</td>
                          <td className="p-1.5 tabular-nums text-gray-600">
                            {c.times_assessed}
                          </td>
                          <td className="p-1.5 tabular-nums text-gray-600">
                            {c.questions}
                          </td>
                          <td
                            className={`p-1.5 tabular-nums font-semibold ${
                              c.avg_pct == null
                                ? "text-gray-400"
                                : c.avg_pct >= 70
                                ? "text-green-700"
                                : c.avg_pct >= 50
                                ? "text-amber-600"
                                : "text-red-600"
                            }`}
                          >
                            {c.avg_pct == null ? "—" : `${c.avg_pct}%`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </main>
  );
}

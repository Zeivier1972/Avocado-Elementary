"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);
const DOW_TODAY = ["", "Mon", "Tue", "Wed", "Thu", "Fri", ""][new Date().getDay()];

function fmt(t: string) {
  // "13:05" -> "1:05"
  const [h, m] = t.split(":").map(Number);
  const hr = ((h + 11) % 12) + 1;
  return `${hr}:${String(m).padStart(2, "0")}`;
}
function span(list: any[]) {
  return list.map((x) => `${fmt(x.start)}–${fmt(x.end)}`).join(", ");
}

export default function SchedulePage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [byGrade, setByGrade] = useState<Record<string, any[]>>({});
  const [mathOnly, setMathOnly] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  // collaborative planning (A/B rotation)
  const [collab, setCollab] = useState<any>(null);
  const [collabBusy, setCollabBusy] = useState(false);

  // visit planner
  const [planKind, setPlanKind] = useState("math");
  const [planGrade, setPlanGrade] = useState("");
  const [planMin, setPlanMin] = useState(30);
  const [visits, setVisits] = useState<any[] | null>(null);
  const [planBusy, setPlanBusy] = useState(false);

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
        return api.getSchedule();
      })
      .then((r) => setByGrade(r.by_grade || {}))
      .catch(() => setByGrade({}));
    api.getCollab().then(setCollab).catch(() => setCollab(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadCollabTemplate() {
    setCollabBusy(true);
    try {
      await api.loadCollab();
      setCollab(await api.getCollab());
    } finally {
      setCollabBusy(false);
    }
  }
  async function setHost(id: string, host: string) {
    await api.updateCollab(id, { host });
    setCollab(await api.getCollab());
  }
  async function setWeek(week: string) {
    await api.setCollabWeek(week);
    setCollab(await api.getCollab());
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.importSchedule(form);
      setMsg(
        `Imported ${r.math_teachers} math teachers (${r.teachers} total, ${r.blocks} time blocks).`
      );
      setByGrade((await api.getSchedule()).by_grade || {});
    } catch (err) {
      setMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function buildPlan() {
    setPlanBusy(true);
    try {
      const r = await api.getVisitPlan(planKind, planMin, planGrade);
      setVisits(r.visits || []);
    } catch (err) {
      alert("Could not build plan: " + (err as Error).message);
    } finally {
      setPlanBusy(false);
    }
  }

  const grades = useMemo(
    () => Object.keys(byGrade).sort((a, b) => (a === "K" ? -1 : b === "K" ? 1 : +a - +b)),
    [byGrade]
  );
  const hasData = grades.length > 0;
  const visitsByDay = useMemo(() => {
    const m: Record<string, any[]> = {};
    for (const v of visits || []) (m[v.day] ||= []).push(v);
    for (const d of Object.keys(m)) m[d].sort((a, b) => a.start.localeCompare(b.start));
    return m;
  }, [visits]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <style>{`@media print { .no-print{display:none!important} header{display:none!important} main{padding:0!important} }`}</style>
      <div className="no-print">
        <CoachHeader me={me} active="/schedule" build={build} />
      </div>

      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <div className="flex items-start justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Math &amp; DI Schedule</h1>
            <p className="text-gray-500 text-sm max-w-2xl">
              When each teacher teaches <b>math</b> (your visit windows) and when
              they can run <b>Math DI</b> — during their Science / Social Studies
              block. Built from the school master schedule.
            </p>
          </div>
          <div className="no-print flex items-center gap-2">
            <button
              onClick={() => window.print()}
              className="text-sm font-semibold text-avocado-dark hover:underline"
            >
              🖨 Print
            </button>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              onChange={onUpload}
              className="hidden"
              id="sched-file"
            />
            <label
              htmlFor="sched-file"
              className={`cursor-pointer bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 ${
                busy ? "opacity-60 pointer-events-none" : ""
              }`}
            >
              {busy ? "Importing…" : hasData ? "↻ Re-upload schedule" : "⬆ Upload master schedule"}
            </label>
          </div>
        </div>

        {msg && (
          <div className="no-print text-sm bg-avocado/10 border border-avocado/20 text-avocado-dark rounded-lg px-3 py-2">
            {msg}
          </div>
        )}

        {/* Collaborative planning (A/B rotation) */}
        <div className="bg-white rounded-2xl border border-avocado/30 p-5">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div>
              <div className="font-semibold text-gray-800">
                Collaborative Planning Meetings
              </div>
              <p className="text-xs text-gray-500">
                Your CPT meetings — a two-week A/B rotation. When you meet each
                grade's math team.
              </p>
            </div>
            {collab?.has_data ? (
              <div className="no-print flex items-center gap-2">
                <span className="text-xs text-gray-500">This week is:</span>
                {["A", "B"].map((w) => (
                  <button
                    key={w}
                    onClick={() => setWeek(w)}
                    className={`text-sm font-semibold rounded-lg px-3 py-1.5 border ${
                      collab.current_week === w
                        ? "bg-avocado text-white border-avocado"
                        : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
                    }`}
                  >
                    Week {w}
                  </button>
                ))}
              </div>
            ) : (
              <button
                onClick={loadCollabTemplate}
                disabled={collabBusy}
                className="no-print bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60"
              >
                {collabBusy ? "Setting up…" : "＋ Set up my meeting times"}
              </button>
            )}
          </div>

          {collab?.has_data ? (
            <div className="grid md:grid-cols-2 gap-4 mt-4">
              {["A", "B"].map((wk) => (
                <div
                  key={wk}
                  className={`rounded-xl border ${
                    collab.current_week === wk
                      ? "border-avocado/40 bg-avocado/5"
                      : "border-gray-100"
                  }`}
                >
                  <div className="px-3 py-1.5 border-b border-gray-100 text-sm font-semibold text-gray-700">
                    Week {wk}
                    {collab.current_week === wk && (
                      <span className="text-avocado-dark"> · this week</span>
                    )}
                  </div>
                  <ul className="p-2 space-y-1.5">
                    {(collab.by_week?.[wk] || []).map((m: any) => {
                      const sugg =
                        collab.suggestions?.[m.grade]?.[
                          m.group.includes("ASD") && !m.group.includes("Gen")
                            ? "ASD"
                            : "Gen Ed"
                        ] || [];
                      const options = Array.from(
                        new Set([
                          ...(collab.suggestions?.[m.grade]?.["Gen Ed"] || []),
                          ...(collab.suggestions?.[m.grade]?.["ASD"] || []),
                        ])
                      );
                      return (
                        <li
                          key={m.id}
                          className="text-xs flex items-center gap-2 flex-wrap"
                        >
                          <span className="font-semibold text-gray-800 w-12 tabular-nums">
                            {fmt(m.time)}
                          </span>
                          <span className="text-gray-600 w-8">{m.day}</span>
                          <span className="text-gray-700">
                            {m.grade === "K" ? "Kinder" : `Gr ${m.grade}`}
                            <span className="text-gray-400"> · {m.group}</span>
                          </span>
                          <select
                            value={m.host || ""}
                            onChange={(e) => setHost(m.id, e.target.value)}
                            className="ml-auto no-print border border-gray-200 rounded px-1 py-0.5 text-[11px] max-w-[140px]"
                          >
                            <option value="">host…</option>
                            {options.map((o: string) => (
                              <option key={o} value={o}>
                                {o}
                              </option>
                            ))}
                            {m.host && !options.includes(m.host) && (
                              <option value={m.host}>{m.host}</option>
                            )}
                          </select>
                          {m.host && (
                            <span className="print-only hidden text-gray-600">
                              {m.host}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400 mt-3">
              Click <b>＋ Set up my meeting times</b> to fill in your A/B rotation
              (the days &amp; times from your planning schedule) — no typing. Then
              pick this year&apos;s host teacher for each meeting and set whether
              this week is A or B.
            </p>
          )}
        </div>

        {!hasData ? (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500 text-sm">
            No schedule yet. Upload the <b>Avocado Master Schedule (.xlsx)</b> — I&apos;ll
            pull each K-3 teacher&apos;s math times and their Science/Social-Studies
            (Math-DI) windows.
          </div>
        ) : (
          <>
            <div className="no-print flex items-center gap-3">
              <label className="flex items-center gap-1.5 text-sm text-gray-600">
                <input
                  type="checkbox"
                  checked={mathOnly}
                  onChange={(e) => setMathOnly(e.target.checked)}
                  className="accent-avocado"
                />
                Show only teachers who teach math
              </label>
              <div className="ml-auto flex items-center gap-3 text-xs">
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded bg-avocado/30 inline-block" /> Math
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded bg-blue-100 inline-block" /> DI window
                </span>
                <span className="flex items-center gap-1">
                  <span className="w-3 h-3 rounded bg-emerald-100 inline-block" /> Planning
                </span>
              </div>
            </div>

            {grades.map((g) => {
              const teachers = (byGrade[g] || []).filter(
                (t) => !mathOnly || t.teaches_math
              );
              if (teachers.length === 0) return null;
              return (
                <div
                  key={g}
                  className="bg-white rounded-2xl border border-gray-100 overflow-hidden"
                >
                  <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 font-semibold text-gray-800">
                    {GRADE_LABEL(g)}
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs min-w-[760px]">
                      <thead>
                        <tr className="text-left text-gray-500 border-b border-gray-100">
                          <th className="p-2 font-semibold">Teacher</th>
                          {DAYS.map((d) => (
                            <th
                              key={d}
                              className={`p-2 font-semibold ${
                                d === DOW_TODAY ? "text-avocado-dark" : ""
                              }`}
                            >
                              {d}
                              {d === DOW_TODAY ? " • today" : ""}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {teachers.map((t) => (
                          <tr
                            key={t.room + t.teacher}
                            className="border-b border-gray-50 align-top"
                          >
                            <td className="p-2 whitespace-nowrap">
                              <div className="font-semibold text-gray-800">
                                {t.teacher || "—"}
                                {t.program === "ASD" && (
                                  <span className="ml-1 text-[9px] font-mono uppercase bg-purple-50 text-purple-700 border border-purple-200 rounded px-1 py-0.5">
                                    ASD
                                  </span>
                                )}
                              </div>
                              <div className="text-gray-400">
                                {t.room ? `Rm ${t.room}` : ""}
                                {!t.teaches_math ? " · ELA" : ""}
                              </div>
                            </td>
                            {DAYS.map((d) => {
                              const day = t.days?.[d] || {
                                math: [],
                                di: [],
                                planning: [],
                              };
                              const planning = day.planning || [];
                              return (
                                <td
                                  key={d}
                                  className={`p-1.5 ${
                                    d === DOW_TODAY ? "bg-avocado/5" : ""
                                  }`}
                                >
                                  {day.math.length > 0 && (
                                    <div className="rounded bg-avocado/15 text-avocado-dark px-1.5 py-0.5 mb-1">
                                      🧮 {span(day.math)}
                                    </div>
                                  )}
                                  {day.di.length > 0 && (
                                    <div
                                      className="rounded bg-blue-50 text-blue-700 px-1.5 py-0.5 mb-1"
                                      title={day.di
                                        .map((x: any) => x.subject)
                                        .join(", ")}
                                    >
                                      DI {span(day.di)}
                                    </div>
                                  )}
                                  {planning.length > 0 && (
                                    <div
                                      className="rounded bg-emerald-50 text-emerald-700 px-1.5 py-0.5"
                                      title={planning
                                        .map((x: any) => x.subject)
                                        .join(", ")}
                                    >
                                      📋 {span(planning)}
                                    </div>
                                  )}
                                  {day.math.length === 0 &&
                                    day.di.length === 0 &&
                                    planning.length === 0 && (
                                      <span className="text-gray-300">—</span>
                                    )}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              );
            })}
            <p className="text-xs text-gray-400">
              🧮 = math lesson (visit window) · DI = Science/Social-Studies block
              where Math DI can run · 📋 = planning time (K/1: 1:50–3:05; 2/3:
              Math common planning). Times shown as start–end.
            </p>

            {/* Visit planner */}
            <div className="bg-white rounded-2xl border border-avocado/30 p-5">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <div className="font-semibold text-gray-800">
                    Visit planner
                  </div>
                  <p className="text-xs text-gray-500">
                    Auto-build a conflict-free week to catch each math teacher
                    once — during their math lesson, or their Math-DI time.
                  </p>
                </div>
                <div className="no-print flex items-center gap-2 flex-wrap">
                  <select
                    value={planKind}
                    onChange={(e) => setPlanKind(e.target.value)}
                    className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  >
                    <option value="math">Visit math lessons</option>
                    <option value="di">Support Math DI</option>
                  </select>
                  <select
                    value={planGrade}
                    onChange={(e) => setPlanGrade(e.target.value)}
                    className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  >
                    <option value="">All grades</option>
                    {grades.map((g) => (
                      <option key={g} value={g}>
                        {GRADE_LABEL(g)}
                      </option>
                    ))}
                  </select>
                  <select
                    value={planMin}
                    onChange={(e) => setPlanMin(+e.target.value)}
                    className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
                  >
                    {[20, 30, 45, 60].map((m) => (
                      <option key={m} value={m}>
                        {m} min
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={buildPlan}
                    disabled={planBusy}
                    className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-1.5 disabled:opacity-60"
                  >
                    {planBusy ? "Building…" : "Build plan"}
                  </button>
                </div>
              </div>

              {visits && (
                <div className="mt-4">
                  {visits.length === 0 ? (
                    <p className="text-sm text-gray-400">
                      No {planKind === "di" ? "DI" : "math"} blocks to plan for
                      this selection.
                    </p>
                  ) : (
                    <>
                      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
                        {DAYS.map((d) => (
                          <div key={d} className="rounded-xl border border-gray-100">
                            <div
                              className={`px-2 py-1 text-xs font-semibold border-b border-gray-100 ${
                                d === DOW_TODAY
                                  ? "text-avocado-dark bg-avocado/5"
                                  : "text-gray-600 bg-gray-50"
                              }`}
                            >
                              {d}
                            </div>
                            <ul className="p-2 space-y-1.5">
                              {(visitsByDay[d] || []).map((v, i) => (
                                <li key={i} className="text-xs">
                                  <div className="font-semibold text-gray-800 tabular-nums">
                                    {fmt(v.start)}–{fmt(v.end)}
                                  </div>
                                  <div className="text-gray-600">
                                    {v.teacher}
                                    {v.program === "ASD" && (
                                      <span className="ml-1 text-[9px] font-mono uppercase text-purple-600">
                                        ASD
                                      </span>
                                    )}{" "}
                                    <span className="text-gray-400">
                                      · {GRADE_LABEL(v.grade)}
                                      {v.room ? ` · Rm ${v.room}` : ""}
                                    </span>
                                  </div>
                                  {planKind === "di" && v.subject && (
                                    <div className="text-[10px] text-blue-600">
                                      during {v.subject}
                                    </div>
                                  )}
                                  {v.conflict && (
                                    <div className="text-[10px] text-red-600">
                                      ⚠ overlaps another visit — adjust
                                    </div>
                                  )}
                                </li>
                              ))}
                              {(visitsByDay[d] || []).length === 0 && (
                                <li className="text-[11px] text-gray-300">—</li>
                              )}
                            </ul>
                          </div>
                        ))}
                      </div>
                      <p className="text-xs text-gray-400 mt-2">
                        {visits.length} visits ·{" "}
                        {planKind === "di"
                          ? "supporting Math DI during Science/Social Studies"
                          : "one math lesson per teacher"}
                        . Re-run to reshuffle; use 🖨 Print for a copy.
                      </p>
                    </>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </main>
  );
}

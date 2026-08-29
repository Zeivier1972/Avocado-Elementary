"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

function pctChip(pct: number | null) {
  if (pct === null || pct === undefined)
    return "bg-gray-100 text-gray-500 border-gray-200";
  if (pct >= 60) return "bg-green-50 text-green-700 border-green-200";
  if (pct >= 40) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-red-50 text-red-700 border-red-200";
}

function barColor(pct: number | null) {
  if (pct === null || pct === undefined) return "#e5e7eb";
  if (pct >= 60) return "#27AE60";
  if (pct >= 40) return "#E67E22";
  return "#C0392B";
}

function initials(name: string) {
  return (
    (name || "")
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((w) => w[0]?.toUpperCase())
      .join("") || "?"
  );
}

const AVATAR_COLORS = [
  "#4a7c2f", "#2E86C1", "#8E44AD", "#C0392B",
  "#E67E22", "#117A65", "#B7791F", "#5D6D7E",
];
function avatarColor(name: string) {
  let h = 0;
  for (const ch of name || "") h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

export default function TeachersPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [audit, setAudit] = useState<any>(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api.health().then(setBuild).catch(() => setBuild(null));
    api.rosterAudit().then(setAudit).catch(() => setAudit(null));
    api
      .me()
      .then((u) => {
        setMe(u);
        return api.teachers();
      })
      .then(setData)
      .catch((e) => setErr((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const teachers = useMemo(() => {
    const list = data?.teachers || [];
    const needle = q.trim().toLowerCase();
    const filtered = needle
      ? list.filter((t: any) => t.name.toLowerCase().includes(needle))
      : list;
    return [...filtered].sort(
      (a: any, b: any) =>
        (a.pct_level_3_plus ?? 999) - (b.pct_level_3_plus ?? 999)
    );
  }, [data, q]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const diag = data?.diagnostics;
  const all = data?.teachers || [];
  const withData = all.filter((t: any) => t.pct_level_3_plus != null);
  const avgL3 = withData.length
    ? Math.round(
        withData.reduce((s: number, t: any) => s + t.pct_level_3_plus, 0) /
          withData.length
      )
    : null;
  const needAttn = all.filter(
    (t: any) => t.pct_level_3_plus != null && t.pct_level_3_plus < 40
  ).length;

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/teachers" build={build} />
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <div className="flex items-end justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-800 tracking-tight">
              Teachers
            </h1>
            <p className="text-gray-500 text-sm">
              Your accounts. Open one to see their students&apos; data and log
              coaching notes. Sorted by who needs you most.
            </p>
          </div>
          <div className="relative">
            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
              🔍
            </span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search teachers…"
              className="border border-gray-200 rounded-lg pl-9 pr-3 py-2 text-sm bg-white w-56 focus:border-avocado focus:outline-none"
            />
          </div>
        </div>

        {/* Summary KPIs */}
        {all.length > 0 && (
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Teachers", value: all.length, tone: "text-gray-800" },
              {
                label: "Avg % at Level 3+",
                value: avgL3 === null ? "—" : `${avgL3}%`,
                tone: "text-avocado-dark",
              },
              {
                label: "Need attention",
                value: needAttn,
                tone: needAttn > 0 ? "text-red-600" : "text-gray-800",
              },
            ].map((k) => (
              <div
                key={k.label}
                className="bg-white rounded-2xl border border-gray-100 p-4 text-center"
              >
                <div className={`text-3xl font-bold tabular-nums ${k.tone}`}>
                  {k.value}
                </div>
                <div className="text-[11px] uppercase tracking-wide text-gray-400 mt-0.5">
                  {k.label}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Roster health — catches bad imports (off-grade students, low coverage) */}
        {audit && (audit.off_grade_students?.length > 0 ||
          audit.teachers?.some((t: any) => t.coverage_pct < 100)) && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="font-semibold text-gray-800 text-sm">
                🩺 Roster health
              </div>
              <div className="text-xs text-gray-400">
                Grades in data:{" "}
                {Object.entries(audit.grade_counts || {})
                  .map(([g, n]: any) => `${g}:${n}`)
                  .join(" · ")}
              </div>
            </div>

            {audit.off_grade_students?.length > 0 && (
              <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3">
                <div className="text-sm font-semibold text-amber-800">
                  ⚠ {audit.off_grade_students.length} student
                  {audit.off_grade_students.length === 1 ? "" : "s"} on a grade
                  the school shouldn&apos;t have (expected{" "}
                  {audit.expected_grades.join(", ")})
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {audit.off_grade_students.map((s: any, i: number) => (
                    <span
                      key={i}
                      className="text-[11px] rounded-full bg-white border border-amber-200 text-amber-800 px-2 py-0.5"
                      title={`${s.teacher} · Grade ${s.grade}`}
                    >
                      {s.student} · Gr {s.grade} · {s.teacher}
                    </span>
                  ))}
                </div>
                <div className="text-[11px] text-amber-700 mt-2">
                  Fix the grade column for these students in the roster file and
                  re-import (Reports → Upload data), or reset the roster.
                </div>
              </div>
            )}

            <div className="mt-3 overflow-x-auto rounded-xl border border-gray-100">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-gray-500 bg-gray-50/80 border-b border-gray-100">
                    <th className="px-3 py-2 font-semibold">Teacher</th>
                    <th className="px-3 py-2 font-semibold">Grade(s)</th>
                    <th className="px-3 py-2 font-semibold">Students</th>
                    <th className="px-3 py-2 font-semibold">FAST coverage</th>
                    <th className="px-3 py-2 font-semibold">% L3+ (of tested)</th>
                  </tr>
                </thead>
                <tbody>
                  {audit.teachers.map((t: any) => (
                    <tr
                      key={t.teacher_id}
                      className="border-b border-gray-50 last:border-0 hover:bg-avocado/5 transition-colors"
                    >
                      <td className="px-3 py-2 font-semibold text-gray-800">
                        {t.name}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={
                            t.off_grade.length > 0 || t.multi_grade
                              ? "text-amber-700 font-semibold"
                              : "text-gray-600"
                          }
                        >
                          {t.grades.join(", ")}
                          {t.off_grade.length > 0 && " ⚠"}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-600">{t.students}</td>
                      <td className="px-3 py-2">
                        <span
                          className={`font-semibold ${
                            t.coverage_pct >= 80
                              ? "text-green-700"
                              : t.coverage_pct >= 40
                              ? "text-amber-600"
                              : "text-red-600"
                          }`}
                        >
                          {t.tested}/{t.students} ({t.coverage_pct}%)
                        </span>
                      </td>
                      <td className="px-3 py-2 text-gray-700">
                        {t.pct_level_3_plus === null
                          ? "—"
                          : `${t.pct_level_3_plus}%`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-gray-400 mt-2">
              Coverage = how many of the teacher&apos;s students actually have a
              FAST Math score. A high &quot;% L3+&quot; on low coverage (e.g. 100%
              of 2 tested) isn&apos;t the whole class.
            </p>
          </div>
        )}

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {teachers.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500 text-sm">
            {diag?.message ||
              "No teachers with linked students yet. Upload the Class Lists workbook on the Planning page."}
          </div>
        ) : (
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {teachers.map((t: any) => (
              <a
                key={t.teacher_id}
                href={`/teachers/${t.teacher_id}`}
                className="bg-white rounded-2xl border border-gray-100 p-5 hover:border-avocado transition block"
              >
                <div className="flex items-start gap-3">
                  <span
                    className="shrink-0 grid place-items-center w-11 h-11 rounded-full text-white font-bold text-sm"
                    style={{ background: avatarColor(t.name) }}
                    aria-hidden
                  >
                    {initials(t.name)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="font-semibold text-gray-800 truncate">
                      {t.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {t.grades?.map(GRADE_LABEL).join(", ")} · {t.students}{" "}
                      students
                    </div>
                    {typeof t.tested === "number" && (
                      <div
                        className={`text-[11px] mt-0.5 ${
                          t.tested < t.students ? "text-amber-600" : "text-gray-400"
                        }`}
                      >
                        {t.tested}/{t.students} tested
                        {t.tested < t.students ? " · partial data" : ""}
                      </div>
                    )}
                  </div>
                  <span
                    className={`text-xs font-bold px-2 py-1 rounded-full border tabular-nums ${pctChip(
                      t.pct_level_3_plus
                    )}`}
                  >
                    {t.pct_level_3_plus === null
                      ? "no data"
                      : `${t.pct_level_3_plus}% L3+`}
                  </span>
                </div>
                <div className="mt-3 h-2 bg-gray-100 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${t.pct_level_3_plus ?? 0}%`,
                      background: barColor(t.pct_level_3_plus),
                    }}
                  />
                </div>
                <div className="mt-2 flex items-center justify-between text-xs">
                  <span className="text-gray-400">
                    {t.fast_math_period
                      ? `FAST Math · ${t.fast_math_period}`
                      : "FAST Math · baseline"}
                  </span>
                  {t.pct_level_3_plus != null &&
                    (t.tested < t.students * 0.5 ? (
                      <span className="font-semibold text-gray-400">
                        Low coverage
                      </span>
                    ) : (
                      <span
                        className={`font-semibold ${
                          t.pct_level_3_plus >= 60
                            ? "text-green-700"
                            : t.pct_level_3_plus >= 40
                            ? "text-amber-600"
                            : "text-red-600"
                        }`}
                      >
                        {t.pct_level_3_plus >= 60
                          ? "On track"
                          : t.pct_level_3_plus >= 40
                          ? "Watch"
                          : "Needs support"}
                      </span>
                    ))}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

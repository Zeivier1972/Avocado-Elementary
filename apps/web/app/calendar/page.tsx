"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

const GRADES = ["K", "1", "2", "3"];
const DOW = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const KIND_STYLE: Record<string, string> = {
  lesson: "bg-avocado/10 text-avocado-dark border-avocado/30",
  review: "bg-yellow-50 text-yellow-800 border-yellow-200",
  assessment: "bg-red-50 text-red-700 border-red-200",
  note: "bg-gray-100 text-gray-600 border-gray-200",
};

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

export default function CalendarPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [grade, setGrade] = useState("3");
  const [cursor, setCursor] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });
  const [entries, setEntries] = useState<any[]>([]);
  const [startDate, setStartDate] = useState(iso(new Date()));
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api.me().then(setMe).catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function load() {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const last = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0);
    try {
      const r = await api.getCalendar(grade, "MATH", iso(first), iso(last));
      setEntries(r.entries || []);
    } catch {
      setEntries([]);
    }
  }

  useEffect(() => {
    if (me) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me, grade, cursor]);

  async function generate() {
    if (
      !confirm(
        `Generate the ${grade === "K" ? "Kindergarten" : `Grade ${grade}`} pacing calendar from ${startDate}? This replaces the current calendar for this grade.`
      )
    )
      return;
    setBusy(true);
    try {
      const r = await api.generateCalendar({
        grade_level: grade,
        subject: "MATH",
        start_date: startDate,
      });
      // jump the view to the start month
      const sd = new Date(startDate + "T00:00:00");
      setCursor(new Date(sd.getFullYear(), sd.getMonth(), 1));
      await load();
      alert(`Scheduled ${r.created} days across ${r.topics} topics.`);
    } catch (err) {
      alert("Generate failed: " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const byDate = useMemo(() => {
    const m: Record<string, any[]> = {};
    for (const e of entries) (m[e.date] ||= []).push(e);
    return m;
  }, [entries]);

  // Build the month grid (weeks of 7 days, Sun-Sat).
  const weeks = useMemo(() => {
    const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
    const start = new Date(first);
    start.setDate(1 - first.getDay());
    const cells: Date[] = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      cells.push(d);
    }
    const rows: Date[][] = [];
    for (let i = 0; i < 42; i += 7) rows.push(cells.slice(i, i + 7));
    // drop trailing all-other-month week
    return rows.filter((row) =>
      row.some((d) => d.getMonth() === cursor.getMonth())
    );
  }, [cursor]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const monthLabel = cursor.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
  const todayIso = iso(new Date());

  return (
    <main className="min-h-screen">
      <style>{`
        @media print {
          .no-print { display: none !important; }
          header { display: none !important; }
          main { padding: 0 !important; }
          .cal-grid { break-inside: avoid; }
        }
      `}</style>
      <header className="no-print bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">Pacing Calendar</span>
        </div>
        <div className="flex items-center gap-4">
          <a href="/coach" className="text-sm text-avocado-dark hover:underline">Planning</a>
          <a href="/reports" className="text-sm text-avocado-dark hover:underline">📊 Reports</a>
          <a href="/goal" className="text-sm text-avocado-dark hover:underline">🎯 Goal</a>
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

      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <h1 className="text-xl font-bold text-gray-800 no-print">Pacing Calendar</h1>

        {/* Grade tabs */}
        <div className="flex gap-2 no-print">
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
              {g === "K" ? "Kindergarten" : `Grade ${g}`}
            </button>
          ))}
        </div>

        {/* Generate control */}
        <div className="no-print bg-white rounded-xl border border-gray-100 p-4 flex flex-wrap items-center gap-3">
          <div className="text-sm text-gray-600">
            Generate the day-by-day schedule from the topics' lessons, starting:
          </div>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="border border-gray-200 rounded px-2 py-1 text-sm"
          />
          <button
            onClick={generate}
            disabled={busy}
            className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60"
          >
            {busy ? "Generating…" : "Generate calendar"}
          </button>
          <div className="flex items-center gap-3 ml-auto text-xs">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-avocado/30 inline-block" /> Lesson</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-yellow-200 inline-block" /> Review</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded bg-red-200 inline-block" /> Assessment</span>
          </div>
        </div>

        {/* Month navigation */}
        <div className="flex items-center justify-between">
          <button
            onClick={() =>
              setCursor(new Date(cursor.getFullYear(), cursor.getMonth() - 1, 1))
            }
            className="no-print text-sm text-avocado-dark hover:underline"
          >
            ← Prev
          </button>
          <div className="font-semibold text-gray-800">
            {grade === "K" ? "Kindergarten" : `Grade ${grade}`} · {monthLabel}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => window.print()}
              className="no-print text-sm font-semibold text-avocado-dark hover:underline"
            >
              🖨 Print
            </button>
            <button
              onClick={() =>
                setCursor(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1))
              }
              className="no-print text-sm text-avocado-dark hover:underline"
            >
              Next →
            </button>
          </div>
        </div>

        {/* Calendar grid */}
        <div className="cal-grid bg-white rounded-xl border border-gray-100 overflow-hidden">
          <div className="grid grid-cols-7 text-xs font-semibold text-gray-500 border-b border-gray-100">
            {DOW.map((d) => (
              <div key={d} className="px-2 py-1 text-center">
                {d}
              </div>
            ))}
          </div>
          {weeks.map((row, ri) => (
            <div key={ri} className="grid grid-cols-7">
              {row.map((d) => {
                const inMonth = d.getMonth() === cursor.getMonth();
                const key = iso(d);
                const dayEntries = byDate[key] || [];
                return (
                  <div
                    key={key}
                    className={`min-h-[92px] border border-gray-50 p-1 align-top ${
                      inMonth ? "" : "bg-gray-50/50"
                    }`}
                  >
                    <div
                      className={`text-[11px] mb-0.5 ${
                        key === todayIso
                          ? "font-bold text-avocado-dark"
                          : inMonth
                          ? "text-gray-500"
                          : "text-gray-300"
                      }`}
                    >
                      {d.getDate()}
                    </div>
                    <div className="space-y-0.5">
                      {dayEntries.map((e) => (
                        <div
                          key={e.id}
                          title={`${e.topic_code} ${e.lesson_code} ${e.title}`}
                          className={`text-[10px] leading-tight rounded border px-1 py-0.5 truncate ${
                            KIND_STYLE[e.kind] || KIND_STYLE.note
                          }`}
                        >
                          {e.lesson_code ? `${e.lesson_code} ` : ""}
                          {e.title}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ))}
        </div>

        {entries.length === 0 && (
          <p className="text-sm text-gray-400">
            No calendar for this grade/month yet. Set a start date and click
            "Generate calendar" — it schedules each topic's lessons across school
            days (weekends skipped), with a review and assessment after each topic.
          </p>
        )}
      </div>
    </main>
  );
}

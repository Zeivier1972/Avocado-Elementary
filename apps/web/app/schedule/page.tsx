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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const grades = useMemo(
    () => Object.keys(byGrade).sort((a, b) => (a === "K" ? -1 : b === "K" ? 1 : +a - +b)),
    [byGrade]
  );
  const hasData = grades.length > 0;

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
                              </div>
                              <div className="text-gray-400">
                                {t.room ? `Rm ${t.room}` : ""}
                                {!t.teaches_math ? " · ELA" : ""}
                              </div>
                            </td>
                            {DAYS.map((d) => {
                              const day = t.days?.[d] || { math: [], di: [] };
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
                                      className="rounded bg-blue-50 text-blue-700 px-1.5 py-0.5"
                                      title={day.di
                                        .map((x: any) => x.subject)
                                        .join(", ")}
                                    >
                                      DI {span(day.di)}
                                    </div>
                                  )}
                                  {day.math.length === 0 &&
                                    day.di.length === 0 && (
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
              where Math DI can run. Times shown as start–end.
            </p>
          </>
        )}
      </div>
    </main>
  );
}

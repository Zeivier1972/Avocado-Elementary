"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) =>
  g === "K"
    ? "Kindergarten"
    : g === "PK"
    ? "Pre-K"
    : g === "VPK"
    ? "VPK"
    : `Grade ${g}`;

function fmt(t: string) {
  const [h, m] = t.split(":").map(Number);
  const hr = ((h + 11) % 12) + 1;
  return `${hr}:${String(m).padStart(2, "0")}`;
}
function fmtTimes(ranges: string[]) {
  return ranges
    .map((r) => {
      const [a, b] = r.split("-");
      return `${fmt(a)}–${fmt(b)}`;
    })
    .join(", ");
}

const PROGRAM_TINT: Record<string, string> = {
  "": "bg-gray-50 text-gray-600 border-gray-200",
  ASD: "bg-purple-50 text-purple-700 border-purple-200",
  "ASD-Modified": "bg-pink-50 text-pink-700 border-pink-200",
  Reverse: "bg-amber-50 text-amber-700 border-amber-200",
};

export default function StaffPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [byGrade, setByGrade] = useState<Record<string, any[]>>({});
  const [total, setTotal] = useState(0);
  const [mathOnly, setMathOnly] = useState(false);
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
        return api.getStaff();
      })
      .then((r) => {
        setByGrade(r.by_grade || {});
        setTotal(r.total || 0);
      })
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
      const r = await api.importStaff(form);
      setMsg(
        `Imported ${r.staff} staff — ${r.math_teachers} teach math. Section codes are now linked everywhere.`
      );
      const s = await api.getStaff();
      setByGrade(s.by_grade || {});
      setTotal(s.total || 0);
    } catch (err) {
      setMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const grades = Object.keys(byGrade);
  const hasData = total > 0;

  return (
    <main className="min-h-screen bg-gray-50/60">
      <CoachHeader me={me} active="/staff" build={build} />
      <div className="max-w-5xl mx-auto p-6 space-y-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-bold text-gray-800">Staff Directory</h1>
            <p className="text-sm text-gray-500">
              Who owns each class code (K01, 101, A13 …) — grade, program, room,
              and who teaches math. This links section codes to teacher names
              across the schedule and the AI Coach.
            </p>
          </div>
          <div className="flex flex-col items-end gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx"
              onChange={onUpload}
              className="hidden"
              id="staff-file"
            />
            <label
              htmlFor="staff-file"
              className={`cursor-pointer bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 ${
                busy ? "opacity-60 pointer-events-none" : ""
              }`}
            >
              {busy
                ? "Importing…"
                : hasData
                ? "↻ Re-upload roster"
                : "⬆ Upload Staff Roster"}
            </label>
            {hasData && (
              <label className="text-xs text-gray-500 flex items-center gap-1">
                <input
                  type="checkbox"
                  checked={mathOnly}
                  onChange={(e) => setMathOnly(e.target.checked)}
                />
                Math teachers only
              </label>
            )}
          </div>
        </div>

        {msg && (
          <div className="bg-avocado/5 border border-avocado/20 text-avocado-dark rounded-xl p-3 text-sm">
            {msg}
          </div>
        )}

        {!hasData && (
          <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-500">
            No staff yet. Upload your <b>Staff Roster (.xlsx)</b> — the sheet with
            the <span className="font-mono">CLASSROOM TEACHERS</span> list — and
            every class code will be linked to its teacher.
          </div>
        )}

        {grades.map((g) => {
          const rows = (byGrade[g] || []).filter(
            (s) => !mathOnly || s.teaches_math
          );
          if (rows.length === 0) return null;
          return (
            <div
              key={g}
              className="bg-white rounded-xl border border-gray-100 overflow-hidden"
            >
              <div className="px-4 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
                <h2 className="font-bold text-gray-800">{GRADE_LABEL(g)}</h2>
                <span className="text-xs text-gray-400">
                  {rows.filter((r) => r.teaches_math).length} math ·{" "}
                  {rows.length} total
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[11px] uppercase tracking-wide text-gray-500 bg-gray-50/80 border-b border-gray-100">
                      <th className="p-2 font-semibold">Code</th>
                      <th className="p-2 font-semibold">Teacher</th>
                      <th className="p-2 font-semibold">Program</th>
                      <th className="p-2 font-semibold">Room</th>
                      <th className="p-2 font-semibold">🧮 Math time</th>
                      <th className="p-2 font-semibold">🔬 DI window</th>
                      <th className="p-2 font-semibold">Birthday</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((s) => (
                      <tr
                        key={s.section + s.name}
                        className="border-b border-gray-50 last:border-0 align-middle hover:bg-avocado/5 transition-colors"
                      >
                        <td className="p-2">
                          <span className="font-mono font-bold text-gray-700 bg-gray-100 border border-gray-200 rounded px-1.5 py-0.5">
                            {s.section || "—"}
                          </span>
                        </td>
                        <td className="p-2 font-semibold text-gray-800">
                          {s.name}
                        </td>
                        <td className="p-2">
                          <span
                            className={`text-[10px] font-semibold uppercase border rounded px-1.5 py-0.5 ${
                              PROGRAM_TINT[s.program] || PROGRAM_TINT[""]
                            }`}
                          >
                            {s.program || "Gen Ed"}
                          </span>
                        </td>
                        <td className="p-2 text-gray-500">{s.room || "—"}</td>
                        <td className="p-2 text-gray-600 whitespace-nowrap">
                          {s.teaches_math ? (
                            (s.math_times || []).length ? (
                              fmtTimes(s.math_times)
                            ) : (
                              <span className="text-amber-600" title="No matching math block found in the master schedule">
                                not in schedule
                              </span>
                            )
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="p-2 text-gray-600 whitespace-nowrap">
                          {s.teaches_math ? (
                            (s.di_windows || []).length ? (
                              fmtTimes(s.di_windows)
                            ) : (
                              <span className="text-gray-300">—</span>
                            )
                          ) : (
                            <span className="text-gray-300">—</span>
                          )}
                        </td>
                        <td className="p-2 text-gray-500">
                          {s.birthday || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}

        {hasData && (
          <p className="text-xs text-gray-400">
            🧮 marks the teacher who teaches math for that class — that&apos;s who
            you plan and coach with. Codes starting with <b>A</b> are ASD
            sections. Staff names live only in your system, never in the code.
          </p>
        )}
      </div>
    </main>
  );
}

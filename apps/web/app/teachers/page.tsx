"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

function pctChip(pct: number | null) {
  if (pct === null || pct === undefined)
    return "bg-gray-100 text-gray-500";
  if (pct >= 60) return "bg-green-50 text-green-700 border-green-200";
  if (pct >= 40) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-red-50 text-red-700 border-red-200";
}

export default function TeachersPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [q, setQ] = useState("");
  const [err, setErr] = useState("");

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

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/teachers" build={build} />
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-800">Teachers</h1>
            <p className="text-gray-500 text-sm">
              Your accounts. Open one to see their students&apos; data and log
              coaching notes. Sorted by who needs you most.
            </p>
          </div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search teachers…"
            className="border border-gray-200 rounded-lg px-3 py-2 text-sm"
          />
        </div>

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
                className="bg-white rounded-2xl border border-gray-100 p-5 hover:border-avocado hover:shadow-sm transition block"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-semibold text-gray-800 truncate">
                      {t.name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {t.grades?.map(GRADE_LABEL).join(", ")} · {t.students}{" "}
                      students
                    </div>
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
                    className="h-full bg-avocado"
                    style={{ width: `${t.pct_level_3_plus ?? 0}%` }}
                  />
                </div>
                <div className="mt-2 text-xs text-gray-400">
                  {t.fast_math_period
                    ? `FAST Math · ${t.fast_math_period}`
                    : "FAST Math · baseline"}
                </div>
              </a>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

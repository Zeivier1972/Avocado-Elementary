"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import DataSubnav from "@/app/_components/DataSubnav";
import CoachHeader from "@/app/_components/CoachHeader";

const FAST = ["PM1", "PM2", "PM3"];
const IREADY = ["AP1", "AP2", "AP3"];

export default function GoalPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);

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
        return api.schoolGoal();
      })
      .then(setData)
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!me || !data)
    return <div className="p-10 text-gray-500">Loading…</div>;

  const s = data.school;
  const grades = Object.entries(data.by_grade || {});

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/goal" build={build} />

      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <DataSubnav active="/goal" />
        {/* Headline goal */}
        <div className="bg-gradient-to-br from-avocado to-avocado-dark text-white rounded-2xl p-6 shadow-sm">
          <div className="text-sm opacity-80">🎯 School Goal — {data.goal}</div>
          <div className="flex items-end gap-6 mt-2">
            <div>
              <div className="text-5xl font-bold">{s.goal_both_pct}%</div>
              <div className="text-xs opacity-80">
                {s.goal_both_n} of {s.students} students at goal
              </div>
            </div>
            <div className="flex gap-6 pb-1">
              <MiniStat label="FAST Math L3+" trend={s.fast_math} keys={FAST} />
              <MiniStat label="i-Ready Math L3+" trend={s.iready_math} keys={IREADY} />
              <MiniStat label="FAST ELA L3+" trend={s.fast_ela} keys={FAST} />
            </div>
          </div>
        </div>

        {/* By grade */}
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-2">By Grade</h2>
          <div className="grid md:grid-cols-2 gap-4">
            {grades.map(([g, b]: any) => (
              <div key={g} className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <div className="font-bold text-gray-800">
                    {g === "K" ? "Kindergarten" : `Grade ${g}`}
                    <span className="text-xs text-gray-400 font-normal ml-2">
                      {b.students} students
                    </span>
                  </div>
                  <div className="text-right">
                    <div className={`text-2xl font-bold ${b.goal_both_pct >= 50 ? "text-green-600" : "text-red-600"}`}>
                      {b.goal_both_pct}%
                    </div>
                    <div className="text-[10px] text-gray-400">at goal (both L3+)</div>
                  </div>
                </div>
                <TrendRow label="FAST Math" data={b.fast_math} keys={FAST} />
                <TrendRow label="i-Ready Math" data={b.iready_math} keys={IREADY} />
                <TrendRow label="FAST ELA" data={b.fast_ela} keys={FAST} />
              </div>
            ))}
          </div>
        </div>

        <p className="text-xs text-gray-400">
          Goal = students scoring Level 3+ in BOTH FAST Math and i-Ready Math
          (latest window). Upload FAST PM and i-Ready AP files in Reports to
          update. i-Ready proficiency = on grade level or above.
        </p>
      </div>
    </main>
  );
}

function MiniStat({ label, trend, keys }: { label: string; trend: any; keys: string[] }) {
  const present = keys.filter((k) => trend && trend[k]);
  const last = present[present.length - 1];
  return (
    <div>
      <div className="text-xs opacity-80">{label}</div>
      <div className="text-2xl font-bold">
        {last ? `${trend[last].pct}%` : "—"}
      </div>
      <div className="text-[10px] opacity-70">
        {present.map((k) => `${k} ${trend[k].pct}`).join(" → ") || "no data"}
      </div>
    </div>
  );
}

function TrendRow({ label, data, keys }: { label: string; data: any; keys: string[] }) {
  const present = keys.filter((k) => data && data[k]);
  return (
    <div className="flex items-center gap-2 mb-2">
      <div className="w-24 text-xs text-gray-600">{label}</div>
      <div className="flex-1 flex items-end gap-2 h-12">
        {keys.map((k) => {
          const d = data?.[k];
          if (!d)
            return (
              <div key={k} className="flex-1 text-center">
                <div className="h-8 flex items-end justify-center">
                  <div className="w-full bg-gray-100 rounded-t" style={{ height: "4%" }} />
                </div>
                <div className="text-[9px] text-gray-300">{k}</div>
              </div>
            );
          const color = d.pct >= 60 ? "bg-green-500" : d.pct >= 40 ? "bg-yellow-500" : "bg-red-500";
          return (
            <div key={k} className="flex-1 text-center">
              <div className="h-8 flex items-end justify-center">
                <div className={`w-full rounded-t ${color}`} style={{ height: `${Math.max(6, d.pct)}%` }} />
              </div>
              <div className="text-[10px] font-semibold text-gray-700">{d.pct}%</div>
              <div className="text-[9px] text-gray-400">{k}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

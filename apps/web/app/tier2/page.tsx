"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADES = ["K", "1", "2", "3"];
const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

export default function Tier2Page() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [grade, setGrade] = useState("3");

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
        return api.getTier2();
      })
      .then(setData)
      .catch(() => setData({ by_grade: {} }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const words = data?.by_grade?.[grade] || [];

  return (
    <main className="min-h-screen bg-gray-50/60">
      <CoachHeader me={me} active="/tier2" build={build} />
      <div className="max-w-4xl mx-auto p-6 space-y-5">
        <div>
          <h1 className="text-xl font-bold text-gray-800">
            Tier 2 Academic Vocabulary
          </h1>
          <p className="text-sm text-gray-500">
            The cross-curricular academic words (determine, explain, justify,
            represent…) pulled straight from each grade&apos;s B.E.S.T. standards —
            the words students meet in the question stems. <b>This year&apos;s focus.</b>{" "}
            These are automatically built into every planning guide and lesson-plan
            template. Tier 3 (subject-specific) words are handled separately.
          </p>
        </div>

        <div className="flex gap-2">
          {GRADES.map((g) => (
            <button
              key={g}
              onClick={() => setGrade(g)}
              className={`px-4 py-2 rounded-lg text-sm font-semibold ${
                grade === g
                  ? "bg-avocado text-white"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {GRADE_LABEL(g)}
            </button>
          ))}
        </div>

        <div className="bg-white rounded-2xl border border-gray-100 p-5">
          <div className="flex items-center justify-between mb-3">
            <div className="font-bold text-gray-800">
              {GRADE_LABEL(grade)} — {words.length} Tier 2 words
            </div>
            <div className="text-xs text-gray-400">
              Ordered by how often they appear across the standards
            </div>
          </div>
          {words.length === 0 ? (
            <p className="text-sm text-gray-400">
              No standards loaded for this grade yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-gray-500 bg-gray-50/80 border-b border-gray-100">
                    <th className="p-2 font-semibold">Word</th>
                    <th className="p-2 font-semibold">What it means (kid words)</th>
                    <th className="p-2 font-semibold">Appears in</th>
                    <th className="p-2 font-semibold"># uses</th>
                  </tr>
                </thead>
                <tbody>
                  {words.map((w: any) => (
                    <tr key={w.word} className="border-b border-gray-50 last:border-0 align-top hover:bg-avocado/5 transition-colors">
                      <td className="p-2 font-semibold text-avocado-dark capitalize">
                        {w.word}
                      </td>
                      <td className="p-2 text-gray-700">{w.meaning}</td>
                      <td className="p-2 text-gray-500 font-mono text-xs">
                        {(w.standards || []).slice(0, 4).join(", ")}
                        {(w.standards || []).length > 4
                          ? ` +${w.standards.length - 4}`
                          : ""}
                      </td>
                      <td className="p-2 tabular-nums text-gray-500">{w.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <p className="text-xs text-gray-400">
          How to use: post these words, pre-teach them, and require them in student
          talk and sentence frames. Because they repeat across standards and
          subjects, growing them lifts comprehension on every test — not just this
          topic.
        </p>
      </div>
    </main>
  );
}

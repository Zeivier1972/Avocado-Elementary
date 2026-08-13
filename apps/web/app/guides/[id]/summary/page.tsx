"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken, downloadGuideSummaryDocx } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

export default function GuideSummaryPage() {
  const router = useRouter();
  const params = useParams();
  const id = params?.id as string;
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
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
        return api.guideSummary(id);
      })
      .then(setData)
      .catch((e) => setErr((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const s = data?.summary;
  const n = data?.narrative;

  return (
    <main className="min-h-screen">
      <style>{`
        @media print {
          .no-print { display: none !important; }
          header { display: none !important; }
          main { padding: 0 !important; }
          .sheet { box-shadow: none !important; border: none !important; }
        }
      `}</style>
      <div className="no-print">
        <CoachHeader me={me} active="/coach" build={build} />
      </div>

      <div className="max-w-3xl mx-auto p-6">
        <div className="no-print flex items-center justify-between mb-4">
          <a href="/coach" className="text-sm text-avocado-dark hover:underline">
            ← Planning
          </a>
          <div className="flex gap-3">
            <button
              onClick={() => window.print()}
              className="text-sm font-semibold text-avocado-dark hover:underline"
            >
              🖨 Print
            </button>
            <button
              onClick={() =>
                downloadGuideSummaryDocx(id, data?.title).catch((e) =>
                  alert("Download failed: " + (e as Error).message)
                )
              }
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-1.5"
            >
              ⬇ Download Word
            </button>
          </div>
        </div>

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {s && (
          <div className="sheet bg-white rounded-2xl border border-gray-100 p-8 space-y-5">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-avocado-dark">
                Coach One-Pager
              </div>
              <h1 className="text-2xl font-bold text-gray-800">{s.title}</h1>
              <p className="text-sm text-gray-500">
                Grade {s.grade_level} {s.subject} · {s.lesson_count} lessons
                {s.assessment_date ? ` · ${s.assessment_date}` : ""}
              </p>
            </div>

            {n?.big_idea && (
              <div className="rounded-xl bg-avocado/5 border border-avocado/20 p-4">
                <div className="font-semibold text-avocado-dark">
                  Big idea — what teachers must understand
                </div>
                <p className="text-gray-700 mt-1">{n.big_idea}</p>
                {n.why_it_matters && (
                  <p className="text-sm text-gray-600 mt-2">
                    <span className="font-semibold">Why it matters: </span>
                    {n.why_it_matters}
                  </p>
                )}
              </div>
            )}

            {n?.talking_points?.length > 0 && (
              <Section title="How to present it — your talking points">
                <ol className="list-decimal ml-5 space-y-1 text-gray-700">
                  {n.talking_points.map((t: string, i: number) => (
                    <li key={i}>{t}</li>
                  ))}
                </ol>
              </Section>
            )}

            {s.strategies?.length > 0 && (
              <Section title="Strategies to reinforce">
                <ul className="space-y-2">
                  {s.strategies.map((st: any, i: number) => (
                    <li key={i} className="text-gray-700">
                      <span className="font-semibold">{st.name}</span> — {st.what}
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            <div className="grid sm:grid-cols-2 gap-4">
              {s.vocabulary?.length > 0 && (
                <Section title="Vocabulary (from the pacing guide)">
                  <div className="flex flex-wrap gap-1.5">
                    {s.vocabulary.map((v: string) => (
                      <span
                        key={v}
                        className="text-xs bg-blue-50 text-blue-700 border border-blue-100 rounded px-2 py-0.5"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </Section>
              )}
              {s.sentence_frames?.length > 0 && (
                <Section title="Sentence frames / stems">
                  <ul className="text-sm text-gray-700 space-y-1">
                    {s.sentence_frames.map((f: string, i: number) => (
                      <li key={i}>“{f}”</li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>

            {(n?.watch_fors?.length > 0 || s.misconceptions?.length > 0) && (
              <Section title="Watch-fors — misconceptions to flag">
                {n?.watch_fors?.length > 0 ? (
                  <ul className="list-disc ml-5 text-gray-700 space-y-1">
                    {n.watch_fors.map((w: string, i: number) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                ) : null}
                {s.misconceptions?.length > 0 && (
                  <table className="w-full text-xs border border-gray-100 mt-2">
                    <thead>
                      <tr className="bg-red-50 text-left text-gray-600">
                        <th className="p-1.5 font-semibold">Misconception</th>
                        <th className="p-1.5 font-semibold">Fix</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.misconceptions.map((m: any, i: number) => (
                        <tr key={i} className="border-t border-gray-100 align-top">
                          <td className="p-1.5 text-gray-700">{m.misconception}</td>
                          <td className="p-1.5 text-gray-700">{m.fix}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </Section>
            )}

            {s.level3?.problem && (
              <Section title="What a Level 3 (on-grade) looks like">
                <p className="text-gray-700">
                  <span className="font-semibold">Problem:</span> {s.level3.problem}
                  {s.level3.solution ? ` → ${s.level3.solution}` : ""}
                </p>
                {s.level3.student_explanation && (
                  <p className="text-sm text-gray-600 mt-1 italic">
                    “{s.level3.student_explanation}”
                  </p>
                )}
              </Section>
            )}

            {s.lessons?.length > 0 && (
              <Section title="Lessons at a glance">
                <div className="overflow-x-auto">
                  <table className="w-full text-xs border border-gray-100">
                    <thead>
                      <tr className="bg-gray-50 text-left text-gray-500">
                        <th className="p-1.5 font-semibold">#</th>
                        <th className="p-1.5 font-semibold">Learning goal</th>
                        <th className="p-1.5 font-semibold">Model this</th>
                        <th className="p-1.5 font-semibold">Exit ticket</th>
                      </tr>
                    </thead>
                    <tbody>
                      {s.lessons.map((L: any, i: number) => (
                        <tr key={i} className="border-t border-gray-100 align-top">
                          <td className="p-1.5 font-medium text-gray-700 whitespace-nowrap">
                            {L.code}
                          </td>
                          <td className="p-1.5 text-gray-700">
                            {L.learning_goal || L.title}
                          </td>
                          <td className="p-1.5 text-gray-600">{L.model_focus}</td>
                          <td className="p-1.5 text-gray-600">{L.exit}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {n && !n.ai_generated && (
              <p className="no-print text-[11px] text-gray-400">
                Talking points generated from your guide. Turn on the AI key for a
                tailored presentation narrative.
              </p>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

function Section({ title, children }: any) {
  return (
    <div>
      <div className="font-semibold text-gray-800 border-b border-gray-100 pb-1 mb-2">
        {title}
      </div>
      {children}
    </div>
  );
}

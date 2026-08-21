"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

function DiFocusInner() {
  const router = useRouter();
  const params = useSearchParams();
  const grade = params.get("grade") || "";
  const standard = params.get("standard") || "";
  const formId = params.get("form_id") || "";
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
        return api.diFocus(grade, standard, formId);
      })
      .then(setData)
      .catch((e) => setErr((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [grade, standard, formId]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const s = data?.standard;

  return (
    <main className="min-h-screen bg-gray-50/60">
      <CoachHeader me={me} active="" build={build} />
      <div className="max-w-4xl mx-auto p-6 space-y-5">
        <div>
          <a href="/assessments" className="text-sm text-avocado-dark hover:underline">
            ← Assessments
          </a>
          <h1 className="text-xl font-bold text-gray-800 mt-1">
            DI Focus — {GRADE_LABEL(grade)}
          </h1>
          <p className="text-sm text-gray-500">
            One place to plan reteach for a weak standard: what it is, the Tier 2
            words to grow, the questions students missed, and a Red / Yellow / Green
            plan using the ACES gradual-release model.
          </p>
        </div>

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {s && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-avocado-dark">
              Standard
            </div>
            <div className="font-mono font-bold text-gray-800 text-lg">{s.code}</div>
            <p className="text-gray-700 mt-1">{s.description}</p>
            {s.ald_level3 && (
              <p className="text-sm text-gray-600 mt-2">
                <span className="font-semibold">What Level 3 looks like: </span>
                {s.ald_level3}
              </p>
            )}
          </div>
        )}

        {data?.tier2?.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-blue-700">
                Tier 2 academic words to grow (this year&apos;s focus)
              </div>
              <a href="/tier2" className="text-xs text-avocado-dark hover:underline">
                All Tier 2 →
              </a>
            </div>
            <div className="flex flex-wrap gap-2 mt-2">
              {data.tier2.map((w: string) => (
                <span
                  key={w}
                  className="text-sm font-semibold capitalize bg-blue-50 text-blue-700 border border-blue-100 rounded-full px-3 py-1"
                >
                  {w}
                </span>
              ))}
            </div>
          </div>
        )}

        {data?.most_missed?.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wide text-red-700">
                Most-missed questions on this standard
              </div>
              <a
                href="/assessments"
                className="text-xs text-avocado-dark hover:underline"
              >
                Open Assessments →
              </a>
            </div>
            <ul className="mt-2 space-y-2">
              {data.most_missed.map((m: any, i: number) => (
                <li key={i} className="text-sm text-gray-700">
                  <span className="font-semibold">Q{m.position}</span>{" "}
                  <span className="text-red-600 font-semibold">
                    ({m.miss_pct}% missed)
                  </span>{" "}
                  {m.topic ? <span className="text-gray-400">· {m.topic}</span> : null}
                  {m.stem && <div className="text-gray-600 mt-0.5">{m.stem}</div>}
                </li>
              ))}
            </ul>
            <p className="text-xs text-gray-400 mt-2">
              Build your DI packet around these exact questions.
            </p>
          </div>
        )}

        {data?.scaffold?.length > 0 && (
          <div className="grid md:grid-cols-3 gap-4">
            {data.scaffold.map((t: any) => (
              <div
                key={t.tier}
                className="bg-white rounded-2xl border p-4"
                style={{ borderTopColor: `#${t.hex}`, borderTopWidth: 4 }}
              >
                <div className="font-bold" style={{ color: `#${t.hex}` }}>
                  {t.tier}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{t.goal}</p>
                <ul className="list-disc ml-4 mt-2 space-y-1 text-sm text-gray-700">
                  {t.moves.map((mv: string, i: number) => (
                    <li key={i}>{mv}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}

export default function DiFocusPage() {
  return (
    <Suspense fallback={<div className="p-10 text-gray-500">Loading…</div>}>
      <DiFocusInner />
    </Suspense>
  );
}

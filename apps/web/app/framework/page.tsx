"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

export default function FrameworkPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [open, setOpen] = useState<string>("");

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
        return api.getFramework();
      })
      .then((r) => {
        setData(r);
        setOpen(r.this_week?.component_key || r.framework?.components?.[0]?.key);
      })
      .catch(() => setData(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const compByKey = useMemo(() => {
    const m: Record<string, any> = {};
    for (const c of data?.framework?.components || []) m[c.key] = c;
    return m;
  }, [data]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const fw = data?.framework;
  const tw = data?.this_week;

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/framework" build={build} />
      <div className="max-w-4xl mx-auto p-6 space-y-5">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">
            Framework of Effective Instruction
          </h1>
          <p className="text-gray-500 text-sm max-w-2xl">
            {fw?.intro ||
              "The coaching lens for planning and growth. Each week leads with one component."}
          </p>
        </div>

        {/* This week's lens */}
        {tw && (
          <div className="rounded-2xl border border-avocado/30 bg-avocado/5 p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-avocado-dark">
              This week&apos;s coaching lens · Week {tw.week}
            </div>
            <div className="text-xl font-bold text-gray-800 mt-1">
              {tw.component_name}: {tw.focus}
            </div>
            <p className="text-sm text-gray-600 mt-1">{tw.why}</p>
            <p className="text-sm text-gray-500 mt-1 italic">{tw.essence}</p>
            <button
              onClick={() => {
                setOpen(tw.component_key);
                document
                  .getElementById("comp-" + tw.component_key)
                  ?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className="mt-2 text-sm font-semibold text-avocado-dark hover:underline"
            >
              Go deep on {tw.component_name} ↓
            </button>
          </div>
        )}

        {/* Components */}
        <div className="space-y-3">
          {(fw?.components || []).map((c: any) => {
            const isOpen = open === c.key;
            return (
              <div
                key={c.key}
                id={"comp-" + c.key}
                className="bg-white rounded-2xl border border-gray-100 overflow-hidden scroll-mt-20"
              >
                <button
                  onClick={() => setOpen(isOpen ? "" : c.key)}
                  className="w-full text-left px-5 py-4 flex items-center justify-between gap-3 hover:bg-gray-50"
                >
                  <div>
                    <div className="font-bold text-gray-800">{c.name}</div>
                    <div className="text-sm text-gray-500">{c.essence}</div>
                  </div>
                  <span className="text-gray-400 text-lg shrink-0">
                    {isOpen ? "−" : "+"}
                  </span>
                </button>
                {isOpen && (
                  <div className="px-5 pb-5 space-y-4 text-sm">
                    <Block title="In the math classroom" tint="bg-avocado/5">
                      <p className="text-gray-700">{c.in_math}</p>
                    </Block>
                    <div className="grid md:grid-cols-2 gap-4">
                      <List
                        title="Look-fors (coaching evidence)"
                        items={c.coach_lookfors}
                        icon="🔎"
                      />
                      <List
                        title="Coaching questions to ask"
                        items={c.coaching_questions}
                        icon="💬"
                      />
                      <List
                        title="Growth moves"
                        items={c.growth_moves}
                        icon="📈"
                      />
                      <List
                        title="Common pitfalls"
                        items={c.pitfalls}
                        icon="⚠️"
                        muted
                      />
                    </div>
                    <List
                      title="District look-fors (effective teachers…)"
                      items={c.district_lookfors}
                      icon="•"
                      small
                    />
                    {c.connects_to && (
                      <p className="text-xs text-gray-500">
                        <span className="font-semibold">Connects to: </span>
                        {c.connects_to}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Year plan */}
        {data?.weekly_plan?.length > 0 && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="font-semibold text-gray-800 mb-1">
              Weekly focus — the year at a glance
            </div>
            <p className="text-xs text-gray-400 mb-3">
              One lens per week. This is your rhythm for leading growth — the AI
              Coach and your Home page follow it.
            </p>
            <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1">
              {data.weekly_plan.map((w: any) => {
                const here = tw && w.week === tw.week;
                return (
                  <div
                    key={w.week}
                    className={`flex gap-2 text-xs py-1 border-b border-gray-50 ${
                      here ? "bg-avocado/5 rounded px-1 font-semibold" : ""
                    }`}
                  >
                    <span className="text-gray-400 w-8 shrink-0 tabular-nums">
                      W{w.week}
                    </span>
                    <span className="text-avocado-dark w-32 shrink-0">
                      {compByKey[w.component_key]?.name || w.component_key}
                    </span>
                    <span className="text-gray-600">{w.focus}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function Block({ title, children, tint }: any) {
  return (
    <div className={`rounded-lg p-3 ${tint || ""}`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
        {title}
      </div>
      {children}
    </div>
  );
}

function List({ title, items, icon, muted, small }: any) {
  if (!items?.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1">
        {title}
      </div>
      <ul className="space-y-1">
        {items.map((x: string, i: number) => (
          <li
            key={i}
            className={`flex gap-1.5 ${
              muted ? "text-gray-500" : "text-gray-700"
            } ${small ? "text-xs" : "text-sm"}`}
          >
            <span className="shrink-0">{icon}</span>
            <span>{x}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

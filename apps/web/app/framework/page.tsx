"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

export default function FrameworkPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [data, setData] = useState<any>(null);
  const [open, setOpen] = useState<string>("");
  // Apply-to-topic
  const [topics, setTopics] = useState<any[]>([]);
  const [apps, setApps] = useState<any[]>([]);
  const [selGrade, setSelGrade] = useState("3");
  const [selTopic, setSelTopic] = useState("");
  const [genBusy, setGenBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

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
        setOpen(
          r.planning_for?.component_key ||
            r.this_week?.component_key ||
            r.framework?.components?.[0]?.key
        );
      })
      .catch(() => setData(null));
    api.coachDashboard()
      .then((d) => setTopics(d.planning_weeks || []))
      .catch(() => setTopics([]));
    api.frameworkApplications()
      .then((r) => setApps(r.applications || []))
      .catch(() => setApps([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gradeTopics = topics.filter((t) => t.grade_level === selGrade);

  async function generateForTopic() {
    if (!selTopic) return;
    setGenBusy(true);
    setResult(null);
    try {
      const r = await api.frameworkForTopic({
        grade: selGrade,
        topic_code: selTopic,
      });
      setResult(r);
      setApps((await api.frameworkApplications()).applications || []);
    } catch (e) {
      alert("Could not generate: " + (e as Error).message);
    } finally {
      setGenBusy(false);
    }
  }

  const compByKey = useMemo(() => {
    const m: Record<string, any> = {};
    for (const c of data?.framework?.components || []) m[c.key] = c;
    return m;
  }, [data]);

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const fw = data?.framework;
  const tw = data?.planning_for || data?.this_week;
  const teachingNow = data?.this_week;

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
              Plan with teachers this week → for next week · Week {tw.week}
            </div>
            <div className="text-xl font-bold text-gray-800 mt-1">
              {tw.component_name}: {tw.focus}
            </div>
            <p className="text-sm text-gray-600 mt-1">{tw.why}</p>
            <p className="text-sm text-gray-500 mt-1 italic">{tw.essence}</p>
            {teachingNow && (
              <p className="text-xs text-gray-400 mt-2">
                Teachers are teaching Week {teachingNow.week} now (
                {teachingNow.component_name}: {teachingNow.focus}). Your planning
                meetings prep the week ahead.
              </p>
            )}
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

        {/* Apply the lens to a specific topic */}
        <div className="bg-white rounded-2xl border border-avocado/30 p-5">
          <div className="font-semibold text-gray-800">
            Apply this week&apos;s lens to a topic
          </div>
          <p className="text-xs text-gray-500 mb-3">
            Script how the framework focus plays out in the actual math a grade is
            teaching — for your planning meeting. Defaults to next week&apos;s lens
            {tw ? ` (${tw.component_name})` : ""}.
          </p>
          <div className="flex flex-wrap gap-2 items-center">
            <select
              value={selGrade}
              onChange={(e) => {
                setSelGrade(e.target.value);
                setSelTopic("");
              }}
              className="border border-gray-200 rounded-lg px-2 py-2 text-sm"
            >
              {["K", "1", "2", "3", "4"].map((g) => (
                <option key={g} value={g}>
                  {GRADE_LABEL(g)}
                </option>
              ))}
            </select>
            <select
              value={selTopic}
              onChange={(e) => setSelTopic(e.target.value)}
              className="border border-gray-200 rounded-lg px-2 py-2 text-sm min-w-[220px]"
            >
              <option value="">Pick a topic…</option>
              {gradeTopics.map((t) => (
                <option key={t.id} value={t.topic_code}>
                  {t.topic_code}: {t.name}
                </option>
              ))}
            </select>
            <button
              onClick={generateForTopic}
              disabled={genBusy || !selTopic}
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-4 py-2 disabled:opacity-60"
            >
              {genBusy ? "Scripting…" : "Script it"}
            </button>
          </div>
          {gradeTopics.length === 0 && (
            <p className="text-xs text-gray-400 mt-2">
              No topics for {GRADE_LABEL(selGrade)} yet — upload a pacing guide on
              the Planning page first.
            </p>
          )}

          {result && (
            <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50/60 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-avocado-dark">
                {result.component_name} · {GRADE_LABEL(result.grade)} ·{" "}
                {result.topic_code}: {result.topic_name}
              </div>
              <AppView content={result.content} />
            </div>
          )}

          {apps.length > 0 && (
            <div className="mt-4">
              <div className="text-xs font-semibold text-gray-500 mb-1">
                Saved topic applications
              </div>
              <ul className="space-y-1">
                {apps.map((a) => (
                  <li
                    key={a.id}
                    className="text-xs flex items-center justify-between gap-2 border-b border-gray-50 py-1"
                  >
                    <button
                      onClick={() => setResult(a)}
                      className="text-avocado-dark hover:underline text-left"
                    >
                      {GRADE_LABEL(a.grade)} · {a.topic_code}: {a.topic_name} —{" "}
                      {a.component_name}
                    </button>
                    <button
                      onClick={async () => {
                        await api.deleteFrameworkApplication(a.id);
                        setApps(apps.filter((x) => x.id !== a.id));
                      }}
                      className="text-gray-300 hover:text-red-500"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

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

function AppView({ content }: { content: any }) {
  if (!content) return null;
  return (
    <div className="mt-2 space-y-3 text-sm">
      {content.how_it_shows_up && (
        <p className="text-gray-700">{content.how_it_shows_up}</p>
      )}
      <div className="grid md:grid-cols-2 gap-3">
        <List title="Look-fors in this topic" items={content.look_fors} icon="🔎" />
        <List title="Coaching questions" items={content.coaching_questions} icon="💬" />
        <List title="Growth moves" items={content.growth_moves} icon="📈" />
        <List title="Watch-fors" items={content.watch_fors} icon="⚠️" muted />
      </div>
      <List
        title="Say this in the planning meeting"
        items={content.teacher_talking_points}
        icon="🗣"
      />
      {content.ai_generated === false && (
        <p className="text-[11px] text-gray-400">
          Built from the framework component; turn on the AI key for topic-tailored
          scripting.
        </p>
      )}
    </div>
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

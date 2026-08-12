"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);

function pctColor(pct: number | null) {
  if (pct === null || pct === undefined) return "text-gray-400";
  if (pct >= 60) return "text-green-700";
  if (pct >= 40) return "text-amber-600";
  return "text-red-600";
}

export default function CoachHomePage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [home, setHome] = useState<any>(null);
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
        return api.coachHome();
      })
      .then(setHome)
      .catch((e) => {
        setErr((e as Error).message);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function toggle(id: string) {
    await api.toggleNote(id);
    setHome(await api.coachHome());
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const goal = home?.goal?.school || {};
  const byGrade = home?.goal?.by_grade || {};
  const watch = home?.teachers_to_watch || [];
  const followups = home?.followups || [];
  const counts = home?.counts || {};
  const dateLabel = home?.today
    ? new Date(home.today + "T00:00:00").toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
      })
    : "";

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/home" build={build} />
      <div className="max-w-6xl mx-auto p-6 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">
            Good to see you, {me.name?.split(" ")[0] || "Coach"}.
          </h1>
          <p className="text-gray-500">{dateLabel} · your command center</p>
        </div>

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {/* Top row: goal + quick counts */}
        <div className="grid md:grid-cols-3 gap-4">
          <div className="md:col-span-2 bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                  School goal
                </div>
                <div className="text-sm text-gray-600">
                  Level 3+ in BOTH FAST Math and i-Ready Math
                </div>
              </div>
              <a
                href="/goal"
                className="text-sm font-semibold text-avocado-dark hover:underline"
              >
                Open goal →
              </a>
            </div>
            <div className="mt-3 flex items-end gap-6">
              <div>
                <div className="text-4xl font-bold text-avocado-dark tabular-nums">
                  {goal.goal_both_pct ?? 0}%
                </div>
                <div className="text-xs text-gray-500">
                  meeting the goal ({goal.goal_both_n ?? 0} of{" "}
                  {goal.students ?? 0} students)
                </div>
              </div>
              <div className="flex-1 grid grid-cols-4 gap-2">
                {["K", "1", "2", "3"].map((g) => {
                  const b = byGrade[g];
                  const pct = b ? b.goal_both_pct : null;
                  return (
                    <div key={g} className="text-center">
                      <div className="h-16 bg-gray-100 rounded relative overflow-hidden flex items-end">
                        <div
                          className="w-full bg-avocado/70"
                          style={{ height: `${pct ?? 0}%` }}
                        />
                      </div>
                      <div className="text-[11px] mt-1 text-gray-500">{g}</div>
                      <div className="text-xs font-semibold tabular-nums text-gray-700">
                        {pct === null ? "—" : `${pct}%`}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
          <div className="bg-white rounded-2xl border border-gray-100 p-5 grid grid-cols-3 gap-2 content-center">
            {[
              ["Teachers", counts.teachers],
              ["Students", counts.students],
              ["Classes", counts.classes],
            ].map(([label, n]) => (
              <div key={label as string} className="text-center">
                <div className="text-2xl font-bold text-gray-800 tabular-nums">
                  {n ?? "—"}
                </div>
                <div className="text-[11px] text-gray-500">{label}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Second row: teachers to watch + follow-ups */}
        <div className="grid md:grid-cols-2 gap-4">
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between mb-3">
              <div className="font-semibold text-gray-800">
                Teachers to watch
              </div>
              <a
                href="/teachers"
                className="text-sm text-avocado-dark hover:underline"
              >
                All teachers →
              </a>
            </div>
            <p className="text-xs text-gray-400 mb-3">
              Lowest % of students at Level 3+ (FAST Math) — where your coaching
              moves the goal most.
            </p>
            {watch.length === 0 ? (
              <p className="text-sm text-gray-400">
                No teacher data yet. Upload the Class Lists and FAST data to see
                this.
              </p>
            ) : (
              <ul className="space-y-1">
                {watch.map((t: any) => (
                  <li key={t.teacher_id}>
                    <a
                      href={`/teachers/${t.teacher_id}`}
                      className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-gray-50"
                    >
                      <span className="text-sm text-gray-700 truncate">
                        {t.name}
                        <span className="text-gray-400">
                          {" "}
                          · {t.grades?.map(GRADE_LABEL).join(", ")}
                        </span>
                      </span>
                      <span
                        className={`text-sm font-bold tabular-nums ${pctColor(
                          t.pct_level_3_plus
                        )}`}
                      >
                        {t.pct_level_3_plus}%
                      </span>
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="font-semibold text-gray-800 mb-1">
              Your follow-ups
            </div>
            <p className="text-xs text-gray-400 mb-3">
              Next steps you logged on a teacher. Check one off when it&apos;s
              done.
            </p>
            {followups.length === 0 ? (
              <p className="text-sm text-gray-400">
                Nothing due. Open a teacher and add a next step to track it here.
              </p>
            ) : (
              <ul className="space-y-1">
                {followups.map((f: any) => (
                  <li
                    key={f.id}
                    className="flex items-start gap-2 rounded-lg px-2 py-1.5 hover:bg-gray-50"
                  >
                    <input
                      type="checkbox"
                      className="mt-1 accent-avocado"
                      onChange={() => toggle(f.id)}
                    />
                    <div className="min-w-0">
                      <div className="text-sm text-gray-700">{f.body}</div>
                      <div className="text-xs">
                        <a
                          href={`/teachers/${f.teacher_id}`}
                          className="text-avocado-dark hover:underline"
                        >
                          {f.teacher}
                        </a>
                        {f.due_date && (
                          <span
                            className={
                              f.overdue
                                ? "text-red-600 font-semibold"
                                : "text-gray-400"
                            }
                          >
                            {" "}
                            · due{" "}
                            {new Date(
                              f.due_date + "T00:00:00"
                            ).toLocaleDateString(undefined, {
                              month: "short",
                              day: "numeric",
                            })}
                            {f.overdue ? " (overdue)" : ""}
                          </span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "@/lib/api";

const bandColor: Record<string, string> = {
  on_track: "bg-green-100 text-green-800 border-green-200",
  watch: "bg-yellow-100 text-yellow-800 border-yellow-200",
  at_risk: "bg-red-100 text-red-800 border-red-200",
};
const bandDot: Record<string, string> = {
  on_track: "🟢",
  watch: "🟡",
  at_risk: "🔴",
};

export default function Dashboard() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [groups, setGroups] = useState<any[]>([]);
  const [plan, setPlan] = useState<any>(null);
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function refresh() {
    const [d, g] = await Promise.all([api.teacherDashboard(), api.groups()]);
    setDash(d);
    setGroups(g);
  }

  useEffect(() => {
    if (!getToken()) {
      router.push("/");
      return;
    }
    api
      .me()
      .then((u) => {
        setMe(u);
        return refresh();
      })
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setMsg("");
    try {
      const form = new FormData();
      form.append("name", "Exit Ticket " + new Date().toLocaleDateString());
      form.append("source", "EXIT_TICKET");
      form.append("subject", "ELA");
      form.append("grade_level", "3");
      form.append("file", file);
      const res = await api.importAssessment(form);
      setMsg(
        `Imported ${res.imported} results · ${res.groups_formed.length} DI group(s) formed` +
          (res.errors.length ? ` · ${res.errors.length} row error(s)` : "")
      );
      await refresh();
    } catch (err) {
      setMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function makePlan(groupId: string) {
    setBusy(true);
    try {
      const res = await api.generatePlan(groupId);
      setPlan(res);
    } finally {
      setBusy(false);
    }
  }

  if (!me || !dash)
    return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">
            {me.name} · <span className="capitalize">{me.role}</span>
          </span>
        </div>
        <button
          onClick={() => {
            clearToken();
            router.push("/");
          }}
          className="text-sm text-gray-500 hover:text-gray-800"
        >
          Sign out
        </button>
      </header>

      <div className="max-w-6xl mx-auto p-6 space-y-6">
        {/* Snapshot + import */}
        <div className="grid md:grid-cols-3 gap-4">
          <Card title="My Class Right Now">
            {dash.proficiency ? (
              <div className="flex items-center gap-3">
                <div className="text-3xl font-bold">
                  {Math.round(dash.proficiency.overall * 100)}%
                </div>
                <span
                  className={`text-xs px-2 py-1 rounded-full border ${bandColor[dash.proficiency.band]}`}
                >
                  {bandDot[dash.proficiency.band]} {dash.proficiency.band}
                </span>
              </div>
            ) : (
              <p className="text-gray-400 text-sm">No data yet</p>
            )}
            <p className="text-xs text-gray-500 mt-2">
              {dash.classes[0]?.name}
            </p>
          </Card>

          <Card title="Import Exit Ticket">
            <p className="text-xs text-gray-500 mb-2">
              CSV: student_district_id, standard_code, percent_correct
            </p>
            <label className="inline-block bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 cursor-pointer">
              {busy ? "Working…" : "Upload CSV ⬆"}
              <input
                type="file"
                accept=".csv"
                onChange={onImport}
                className="hidden"
                disabled={busy}
              />
            </label>
            {msg && <p className="text-xs text-gray-600 mt-2">{msg}</p>}
          </Card>

          <Card title="Recommended DI Groups">
            {dash.recommended_groups.length ? (
              <ul className="space-y-1 text-sm">
                {dash.recommended_groups.map((g: any, i: number) => (
                  <li key={i} className="flex justify-between">
                    <span>
                      {bandDot[g.band]} {g.standard_code}
                    </span>
                    <span className="text-gray-500">{g.size} students</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-gray-400 text-sm">
                Import data to form groups
              </p>
            )}
          </Card>
        </div>

        {/* Lowest standards */}
        <Card title="Lowest Standards">
          <div className="space-y-2">
            {dash.lowest_standards.map((s: any) => (
              <div
                key={s.standard_id}
                className="flex items-center justify-between border-b border-gray-50 pb-2"
              >
                <div>
                  <span className="font-medium">{s.code}</span>
                  <span className="text-xs text-gray-400 ml-2">
                    {s.subject}
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-600">
                    {Math.round(s.avg_mastery * 100)}%
                  </span>
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full border ${bandColor[s.band]}`}
                  >
                    {bandDot[s.band]}
                  </span>
                  <span className="text-xs text-gray-500 w-24 text-right">
                    {s.students_deficient} deficient
                  </span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        {/* DI Groups + plan */}
        <div className="grid md:grid-cols-2 gap-4">
          <Card title="DI Groups">
            {groups.length === 0 && (
              <p className="text-gray-400 text-sm">No groups yet.</p>
            )}
            <ul className="space-y-2">
              {groups.map((g) => (
                <li
                  key={g.id}
                  className="flex items-center justify-between border border-gray-100 rounded-lg px-3 py-2"
                >
                  <div>
                    <div className="font-medium text-sm">{g.name}</div>
                    <div className="text-xs text-gray-500">
                      {g.members.length} students · {g.status}
                    </div>
                  </div>
                  <button
                    onClick={() => makePlan(g.id)}
                    disabled={busy}
                    className="text-sm bg-avocado-light text-avocado-dark font-semibold rounded-lg px-3 py-1.5 hover:bg-green-200 disabled:opacity-60"
                  >
                    7-Day Plan
                  </button>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Intervention / Enrichment">
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div>
                <div className="text-xs font-semibold text-red-600 mb-1">
                  Needs Intervention
                </div>
                <ul className="space-y-0.5">
                  {dash.needs_intervention.map((s: any) => (
                    <li key={s.student_id} className="text-gray-700">
                      {s.name}
                    </li>
                  ))}
                  {!dash.needs_intervention.length && (
                    <li className="text-gray-400">None</li>
                  )}
                </ul>
              </div>
              <div>
                <div className="text-xs font-semibold text-green-700 mb-1">
                  Needs Enrichment
                </div>
                <ul className="space-y-0.5">
                  {dash.needs_enrichment.map((s: any) => (
                    <li key={s.student_id} className="text-gray-700">
                      {s.name}
                    </li>
                  ))}
                  {!dash.needs_enrichment.length && (
                    <li className="text-gray-400">None</li>
                  )}
                </ul>
              </div>
            </div>
          </Card>
        </div>

        {/* Generated plan */}
        {plan && (
          <Card title={`7-Day DI Plan · ${plan.standard}`}>
            <p className="text-xs text-gray-500 mb-3">
              {plan.plan.ai_generated
                ? `AI-generated draft (${plan.plan.generated_by})`
                : "Structured template draft"}{" "}
              — review &amp; edit before teaching.
            </p>
            {plan.plan.days ? (
              <div className="grid md:grid-cols-2 gap-2">
                {plan.plan.days.map((d: any) => (
                  <div
                    key={d.day}
                    className="border border-gray-100 rounded-lg p-3"
                  >
                    <div className="font-semibold text-sm">
                      Day {d.day}: {d.focus}
                    </div>
                    <p className="text-xs text-gray-600 mt-1">{d.plan}</p>
                    <div className="text-[11px] text-avocado-dark mt-1">
                      {d.artifacts.join(" · ")}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <pre className="text-xs whitespace-pre-wrap text-gray-700">
                {plan.plan.content}
              </pre>
            )}
          </Card>
        )}
      </div>
    </main>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-gray-700 mb-3">{title}</h2>
      {children}
    </div>
  );
}

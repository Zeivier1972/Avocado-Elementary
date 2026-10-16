"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const CAT_META: Record<string, { label: string; cls: string }> = {
  assessment: { label: "Assessment", cls: "bg-red-50 text-red-700 border-red-200" },
  progress_report: { label: "Progress report", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  report_card: { label: "Report card", cls: "bg-blue-50 text-blue-700 border-blue-200" },
  planning_day: { label: "Planning day", cls: "bg-avocado/10 text-avocado-dark border-avocado/30" },
  vertical_planning: { label: "Vertical planning", cls: "bg-avocado/10 text-avocado-dark border-avocado/30" },
  faculty_meeting: { label: "Faculty mtg", cls: "bg-purple-50 text-purple-700 border-purple-200" },
  eesac_meeting: { label: "EESAC", cls: "bg-purple-50 text-purple-700 border-purple-200" },
  drill: { label: "Drill", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  emergency_drill: { label: "Emergency drill", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  custom: { label: "My date", cls: "bg-gray-100 text-gray-600 border-gray-200" },
};

const FILTERS = [
  ["", "All"],
  ["assessment", "Assessments"],
  ["report_card", "Report cards"],
  ["progress_report", "Progress reports"],
  ["planning_day", "Planning days"],
  ["vertical_planning", "Vertical planning"],
  ["faculty_meeting", "Faculty mtgs"],
  ["eesac_meeting", "EESAC"],
  ["drill", "Drills"],
  ["emergency_drill", "Emergency drills"],
  ["custom", "My dates"],
];

function monthKey(iso: string) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}
function dayNum(iso: string) {
  return new Date(iso + "T00:00:00").getDate();
}
function dow(iso: string) {
  return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
    weekday: "short",
  });
}

export default function DatesPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [dates, setDates] = useState<any[]>([]);
  const [filter, setFilter] = useState("");
  const [err, setErr] = useState("");

  // add form
  const [form, setForm] = useState({
    title: "",
    category: "custom",
    date: "",
    end_date: "",
    grade: "",
  });
  const [saving, setSaving] = useState(false);

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
        return api.keyDates();
      })
      .then((r) => setDates(r.dates || []))
      .catch((e) => setErr((e as Error).message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const shown = useMemo(
    () => (filter ? dates.filter((d) => d.category === filter) : dates),
    [dates, filter]
  );

  const groups = useMemo(() => {
    const m: Record<string, any[]> = {};
    for (const d of shown) (m[monthKey(d.date)] ||= []).push(d);
    return m;
  }, [shown]);

  async function reload() {
    const r = await api.keyDates();
    setDates(r.dates || []);
  }

  async function add() {
    if (!form.title.trim() || !form.date) return;
    setSaving(true);
    try {
      await api.addKeyDate(form);
      setForm({ title: "", category: "custom", date: "", end_date: "", grade: "" });
      await reload();
    } catch (e) {
      alert("Could not save: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this date?")) return;
    await api.deleteKeyDate(id);
    setDates(dates.filter((d) => d.id !== id));
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/dates" build={build} />
      <div className="max-w-4xl mx-auto p-6 space-y-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">Key Dates</h1>
          <p className="text-gray-500 text-sm">
            Your school calendar in one place. Upcoming dates surface on Home so
            you&apos;re always ahead. Add your own below.
          </p>
        </div>

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {/* Add a date */}
        <div className="bg-white rounded-2xl border border-gray-100 p-4">
          <div className="flex flex-wrap gap-2 items-end">
            <input
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="Add a date… e.g. Grade 3 data chat"
              className="flex-1 min-w-[200px] border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="border border-gray-200 rounded-lg px-2 py-2 text-sm"
            >
              {FILTERS.slice(1).map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <div className="flex flex-col">
              <label className="text-[10px] text-gray-400">Date</label>
              <input
                type="date"
                value={form.date}
                onChange={(e) => setForm({ ...form, date: e.target.value })}
                className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
              />
            </div>
            <div className="flex flex-col">
              <label className="text-[10px] text-gray-400">End (optional)</label>
              <input
                type="date"
                value={form.end_date}
                onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                className="border border-gray-200 rounded-lg px-2 py-1.5 text-sm"
              />
            </div>
            <button
              onClick={add}
              disabled={saving || !form.title.trim() || !form.date}
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-4 py-2 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Add"}
            </button>
          </div>
        </div>

        {/* Filter */}
        <div className="flex gap-2 flex-wrap">
          {FILTERS.map(([v, l]) => (
            <button
              key={v}
              onClick={() => setFilter(v)}
              className={`px-3 py-1 rounded-full text-xs font-semibold border ${
                filter === v
                  ? "bg-avocado text-white border-avocado"
                  : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
              }`}
            >
              {l}
            </button>
          ))}
        </div>

        {/* Grouped list */}
        {Object.keys(groups).length === 0 ? (
          <p className="text-sm text-gray-400">No dates in this view.</p>
        ) : (
          Object.entries(groups).map(([month, rows]) => (
            <div key={month} className="bg-white rounded-2xl border border-gray-100 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400 mb-2">
                {month}
              </div>
              <ul className="divide-y divide-gray-50">
                {rows.map((d) => {
                  const meta = CAT_META[d.category] || CAT_META.custom;
                  const soon =
                    d.active || (d.days_until !== null && d.days_until >= 0 && d.days_until <= 7);
                  return (
                    <li key={d.id} className="flex items-center gap-3 py-2">
                      <div className="w-12 shrink-0 text-center">
                        <div className="text-[10px] text-gray-400 uppercase">
                          {dow(d.date)}
                        </div>
                        <div className="text-lg font-bold text-gray-800 leading-none tabular-nums">
                          {dayNum(d.date)}
                        </div>
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-700">
                          {d.title}
                          {d.grade && (
                            <span className="text-gray-400"> · {d.grade}</span>
                          )}
                        </div>
                        <div className="mt-0.5 flex items-center gap-2 flex-wrap">
                          <span
                            className={`text-[10px] font-mono uppercase border rounded px-1.5 py-0.5 ${meta.cls}`}
                          >
                            {meta.label}
                          </span>
                          {d.end_date && (
                            <span className="text-[11px] text-gray-400">
                              through{" "}
                              {new Date(
                                d.end_date + "T00:00:00"
                              ).toLocaleDateString(undefined, {
                                month: "short",
                                day: "numeric",
                              })}
                            </span>
                          )}
                          {soon && (
                            <span className="text-[11px] font-semibold text-red-600">
                              {d.active ? "now open" : "this week"}
                            </span>
                          )}
                        </div>
                      </div>
                      {d.source === "custom" && (
                        <button
                          onClick={() => remove(d.id)}
                          className="text-gray-300 hover:text-red-500 text-sm shrink-0"
                          title="Delete"
                        >
                          ✕
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}
      </div>
    </main>
  );
}

"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const GRADE_LABEL = (g: string) => (g === "K" ? "Kindergarten" : `Grade ${g}`);
const KIND_META: Record<string, { label: string; cls: string }> = {
  focus: { label: "Focus area", cls: "bg-avocado/10 text-avocado-dark border-avocado/30" },
  next_step: { label: "Next step", cls: "bg-amber-50 text-amber-700 border-amber-200" },
  note: { label: "Note", cls: "bg-gray-100 text-gray-600 border-gray-200" },
};

function lvl(v: any) {
  return typeof v === "number" ? v : "—";
}
function lvlCls(v: any) {
  if (typeof v !== "number") return "text-gray-300";
  return v >= 3 ? "text-green-700 font-semibold" : "text-red-600";
}

const COLOR_HEX: Record<string, string> = {
  Red: "#C0392B",
  Yellow: "#F1C40F",
  Green: "#27AE60",
  Blue: "#2E86C1",
  Orange: "#E67E22",
};
function ColorChip({ color, children }: { color?: string; children: any }) {
  const hex = color ? COLOR_HEX[color] : undefined;
  return (
    <span
      className="inline-flex items-center text-xs font-semibold rounded px-1.5 py-0.5"
      style={
        hex
          ? { backgroundColor: hex + "22", color: hex, border: `1px solid ${hex}55` }
          : { background: "#f3f4f6", color: "#6b7280" }
      }
    >
      {children}
    </span>
  );
}
function fmt(t: string) {
  const [h, m] = t.split(":").map(Number);
  const hr = ((h + 11) % 12) + 1;
  return `${hr}:${String(m).padStart(2, "0")}`;
}
function fmtTimes(ranges?: string[]) {
  if (!ranges || ranges.length === 0) return "";
  return ranges
    .map((r) => {
      const [a, b] = r.split("-");
      return `${fmt(a)}–${fmt(b)}`;
    })
    .join(", ");
}

export default function TeacherProfilePage() {
  const router = useRouter();
  const params = useParams();
  const id = params?.id as string;
  const [me, setMe] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [rep, setRep] = useState<any>(null);
  const [hub, setHub] = useState<any>(null);
  const [notes, setNotes] = useState<any[]>([]);
  const [err, setErr] = useState("");

  // note form
  const [kind, setKind] = useState("focus");
  const [body, setBody] = useState("");
  const [due, setDue] = useState("");
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
        return Promise.all([api.teacherReport(id), api.teacherNotes(id)]);
      })
      .then(([r, n]) => {
        setRep(r);
        setNotes(n.notes || []);
      })
      .catch((e) => setErr((e as Error).message));
    api.teacherHub(id).then(setHub).catch(() => setHub(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  async function addNote() {
    if (!body.trim()) return;
    setSaving(true);
    try {
      await api.addTeacherNote(id, {
        kind,
        body,
        due_date: kind === "next_step" ? due : "",
      });
      setBody("");
      setDue("");
      const n = await api.teacherNotes(id);
      setNotes(n.notes || []);
    } catch (e) {
      alert("Could not save: " + (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function toggle(nid: string) {
    await api.toggleNote(nid);
    const n = await api.teacherNotes(id);
    setNotes(n.notes || []);
  }
  async function remove(nid: string) {
    if (!confirm("Delete this note?")) return;
    await api.deleteNote(nid);
    setNotes(notes.filter((x) => x.id !== nid));
  }

  if (!me) return <div className="p-10 text-gray-500">Loading…</div>;

  const roster = rep?.roster || [];
  const topicCols: string[] = rep?.topic_columns || [];

  return (
    <main className="min-h-screen">
      <CoachHeader me={me} active="/teachers" build={build} />
      <div className="max-w-6xl mx-auto p-6 space-y-5">
        <div>
          <a href="/teachers" className="text-sm text-avocado-dark hover:underline">
            ← All teachers
          </a>
          <div className="flex items-end justify-between flex-wrap gap-3 mt-1">
            <div>
              <h1 className="text-2xl font-bold text-gray-800">
                {rep?.teacher || "Teacher"}
              </h1>
              <p className="text-gray-500 text-sm">
                {rep?.students ?? 0} students
              </p>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-avocado-dark tabular-nums">
                {rep?.pct_level_3_plus ?? 0}%
              </div>
              <div className="text-xs text-gray-500">at Level 3+ (FAST Math)</div>
            </div>
          </div>
        </div>

        {err && (
          <div className="bg-red-50 border border-red-100 text-red-700 rounded-xl p-4 text-sm">
            {err}
          </div>
        )}

        {/* Connected hub — section, schedule, and topic-test results in one place */}
        {hub && (hub.staff || hub.schedule?.math_times?.length || hub.assessments?.length > 0) && (
          <div className="grid md:grid-cols-3 gap-4">
            {/* Class + schedule */}
            <div className="bg-white rounded-2xl border border-gray-100 p-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                Class &amp; schedule
              </div>
              {hub.staff ? (
                <div className="mt-1">
                  <div className="flex items-center gap-2">
                    {hub.staff.section && (
                      <span className="font-mono font-bold text-gray-700 bg-gray-100 border border-gray-200 rounded px-1.5 py-0.5 text-sm">
                        {hub.staff.section}
                      </span>
                    )}
                    <span className="text-sm text-gray-600">
                      {hub.staff.program}
                      {hub.staff.room ? ` · Rm ${hub.staff.room}` : ""}
                    </span>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-gray-400 mt-1">
                  Not matched in the Staff directory.
                </p>
              )}
              <div className="mt-2 text-sm">
                <div className="text-gray-700">
                  🧮 Math:{" "}
                  <span className="font-medium">
                    {fmtTimes(hub.schedule?.math_times) || "—"}
                  </span>
                </div>
                <div className="text-gray-700">
                  🔬 DI window:{" "}
                  <span className="font-medium">
                    {fmtTimes(hub.schedule?.di_windows) || "—"}
                  </span>
                </div>
              </div>
              <a
                href="/schedule"
                className="text-xs text-avocado-dark hover:underline mt-2 inline-block"
              >
                Open schedule →
              </a>
            </div>

            {/* Latest topic-test result + weakest standard */}
            <div className="md:col-span-2 bg-white rounded-2xl border border-gray-100 p-4">
              <div className="flex items-center justify-between">
                <div className="text-xs font-semibold uppercase tracking-wide text-gray-400">
                  Topic-test results (this class)
                </div>
                <a
                  href="/assessments"
                  className="text-xs text-avocado-dark hover:underline"
                >
                  Assessments →
                </a>
              </div>
              {hub.assessments?.length > 0 ? (
                <div className="mt-2 space-y-2">
                  {hub.assessments.map((a: any) => (
                    <div
                      key={a.form_id}
                      className="border border-gray-100 rounded-xl p-3"
                    >
                      <div className="flex items-center justify-between flex-wrap gap-1">
                        <div className="font-semibold text-gray-800 text-sm">
                          {a.topic}
                          <span className="text-gray-400 font-normal">
                            {" "}
                            · {a.students} students
                          </span>
                        </div>
                        <ColorChip color={a.color}>{a.avg_percent}% avg</ColorChip>
                      </div>
                      {a.weakest_standard && (
                        <div className="text-sm text-gray-600 mt-1">
                          Focus for DI:{" "}
                          <span className="font-mono">
                            {a.weakest_standard.standard}
                          </span>{" "}
                          <ColorChip color={a.weakest_standard.color}>
                            {a.weakest_standard.percent}%
                          </ColorChip>
                        </div>
                      )}
                      {a.most_missed?.length > 0 && (
                        <div className="text-xs text-gray-500 mt-1">
                          Most-missed:{" "}
                          {a.most_missed
                            .map((m: any) => `Q${m.position} (${m.miss_pct}%)`)
                            .join(", ")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-gray-400 mt-2">
                  No topic-test results uploaded for this class yet.{" "}
                  <a href="/assessments" className="text-avocado-dark hover:underline">
                    Upload results →
                  </a>
                </p>
              )}
            </div>
          </div>
        )}

        {/* Coaching notes */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5">
          <div className="font-semibold text-gray-800 mb-1">Coaching notes</div>
          <p className="text-xs text-gray-400 mb-3">
            Capture a focus area, a running note, or a next step. Next steps with
            a due date show up on your Home follow-ups.
          </p>
          <div className="flex flex-wrap gap-2 items-start">
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              className="border border-gray-200 rounded-lg px-2 py-2 text-sm"
            >
              <option value="focus">Focus area</option>
              <option value="note">Note</option>
              <option value="next_step">Next step</option>
            </select>
            <input
              value={body}
              onChange={(e) => setBody(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addNote()}
              placeholder="e.g. Model a CUBS think-aloud in Topic 3"
              className="flex-1 min-w-[220px] border border-gray-200 rounded-lg px-3 py-2 text-sm"
            />
            {kind === "next_step" && (
              <input
                type="date"
                value={due}
                onChange={(e) => setDue(e.target.value)}
                className="border border-gray-200 rounded-lg px-2 py-2 text-sm"
              />
            )}
            <button
              onClick={addNote}
              disabled={saving || !body.trim()}
              className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-4 py-2 disabled:opacity-60"
            >
              {saving ? "Saving…" : "Add"}
            </button>
          </div>

          {notes.length > 0 && (
            <ul className="mt-4 space-y-2">
              {notes.map((n) => {
                const meta = KIND_META[n.kind] || KIND_META.note;
                return (
                  <li
                    key={n.id}
                    className="flex items-start gap-3 border-t border-gray-50 pt-2"
                  >
                    {n.kind === "next_step" && (
                      <input
                        type="checkbox"
                        checked={n.done}
                        onChange={() => toggle(n.id)}
                        className="mt-1 accent-avocado"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <span
                        className={`text-[10px] font-mono uppercase border rounded px-1.5 py-0.5 mr-2 ${meta.cls}`}
                      >
                        {meta.label}
                      </span>
                      <span
                        className={`text-sm ${
                          n.done ? "line-through text-gray-400" : "text-gray-700"
                        }`}
                      >
                        {n.body}
                      </span>
                      <div className="text-[11px] text-gray-400 mt-0.5">
                        {n.created_at
                          ? new Date(n.created_at).toLocaleDateString()
                          : ""}
                        {n.due_date &&
                          ` · due ${new Date(
                            n.due_date + "T00:00:00"
                          ).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                          })}`}
                      </div>
                    </div>
                    <button
                      onClick={() => remove(n.id)}
                      className="text-gray-300 hover:text-red-500 text-sm"
                      title="Delete"
                    >
                      ✕
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Roster tracker */}
        <div className="bg-white rounded-2xl border border-gray-100 p-5">
          <div className="font-semibold text-gray-800 mb-3">
            Student data tracker
          </div>
          {roster.length === 0 ? (
            <p className="text-sm text-gray-400">
              No students linked to this teacher yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs border border-gray-100 min-w-[720px]">
                <thead>
                  <tr className="bg-gray-50 text-left text-gray-500">
                    <th className="p-2 font-semibold">Student</th>
                    <th className="p-2 font-semibold">Gr</th>
                    <th className="p-2 font-semibold" colSpan={3}>
                      FAST Math (PM1/2/3)
                    </th>
                    <th className="p-2 font-semibold">iReady Math</th>
                    <th className="p-2 font-semibold">Topic avg</th>
                    {topicCols.map((c) => (
                      <th key={c} className="p-2 font-semibold">
                        {c}
                      </th>
                    ))}
                    <th className="p-2 font-semibold">Flags</th>
                  </tr>
                </thead>
                <tbody>
                  {roster.map((s: any) => {
                    const ir =
                      s.iready_math?.AP3 ??
                      s.iready_math?.AP2 ??
                      s.iready_math?.AP1;
                    return (
                      <tr
                        key={s.student_id}
                        className={`border-t border-gray-100 align-top ${
                          s.l25 ? "bg-red-50/40" : ""
                        }`}
                      >
                        <td className="p-2 text-gray-700 whitespace-nowrap">
                          {s.name}
                        </td>
                        <td className="p-2 text-gray-500">{s.grade}</td>
                        {["PM1", "PM2", "PM3"].map((p) => (
                          <td
                            key={p}
                            className={`p-2 ${lvlCls(s.fast_math?.[p])}`}
                          >
                            {lvl(s.fast_math?.[p])}
                          </td>
                        ))}
                        <td className={`p-2 ${lvlCls(ir)}`}>{lvl(ir)}</td>
                        <td className="p-2 text-gray-600 tabular-nums">
                          {s.topic_avg === null ? "—" : `${s.topic_avg}%`}
                        </td>
                        {topicCols.map((c) => (
                          <td key={c} className="p-2 text-gray-500 tabular-nums">
                            {s.topics?.[c] === undefined
                              ? "—"
                              : `${s.topics[c]}%`}
                          </td>
                        ))}
                        <td className="p-2 text-gray-500 whitespace-nowrap">
                          {s.ell ? "ELL " : ""}
                          {s.ese ? "ESE " : ""}
                          {s.l25 ? "L25" : ""}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <p className="text-[11px] text-gray-400 mt-2">
                Green = Level 3+ (on grade). Red-tinted rows are the lowest 25%
                by latest FAST Math.
              </p>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

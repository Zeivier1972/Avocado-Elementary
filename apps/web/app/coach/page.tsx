"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  clearToken,
  downloadDocument,
  downloadGuideDocx,
  getToken,
} from "@/lib/api";

const GRADES = ["K", "1", "2", "3"];

export default function CoachPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [dash, setDash] = useState<any>(null);
  const [build, setBuild] = useState<any>(null);
  const [topic, setTopic] = useState<any>(null);
  const [guide, setGuide] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [grade, setGrade] = useState("3");
  const [summary, setSummary] = useState<any>(null);
  const [rosterMsg, setRosterMsg] = useState("");
  const [docs, setDocs] = useState<any>({});
  const [docBusy, setDocBusy] = useState("");
  const [showNew, setShowNew] = useState(false);
  const [savedGuides, setSavedGuides] = useState<any>({});

  async function loadGuides(g: string) {
    try {
      const r = await api.listGuides(g);
      setSavedGuides(r.folders || {});
    } catch {
      setSavedGuides({});
    }
  }

  async function openSavedGuide(id: string) {
    setTopic(null);
    try {
      const r = await api.getGuide(id);
      setGuide(r.guide);
    } catch (err) {
      alert("Could not open guide: " + (err as Error).message);
    }
  }

  async function removeSavedGuide(id: string) {
    if (!confirm("Delete this saved guide?")) return;
    try {
      await api.deleteGuide(id);
      await loadGuides(grade);
    } catch (err) {
      alert("Delete failed: " + (err as Error).message);
    }
  }

  async function createTopic(payload: any) {
    await api.createTopic({ grade_level: grade, subject: "MATH", ...payload });
    const d = await api.coachDashboard();
    setDash(d);
    setShowNew(false);
  }

  async function loadDocs(g: string) {
    try {
      const r = await api.listDocuments(g);
      setDocs(r.folders || {});
    } catch {
      setDocs({});
    }
  }

  async function uploadDoc(
    e: React.ChangeEvent<HTMLInputElement>,
    topicCode: string
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    setDocBusy(topicCode || "_grade");
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("grade_level", grade);
      form.append("topic_code", topicCode || "");
      form.append("subject", "MATH");
      await api.uploadDocument(form);
      await loadDocs(grade);
    } catch (err) {
      alert("Upload failed: " + (err as Error).message);
    } finally {
      setDocBusy("");
      e.target.value = "";
    }
  }

  async function uploadPacingAndGenerate(
    e: React.ChangeEvent<HTMLInputElement>
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    const base = file.name.replace(/\.[^.]+$/, "");
    const tm = base.match(/(topic|chapter)\s*_?\s*(\d+)/i);
    const suggested = tm ? `${tm[1][0].toUpperCase()}${tm[1].slice(1).toLowerCase()} ${tm[2]}` : base;
    const topicName = window.prompt(
      "Name this topic (e.g., Topic 1: Understand Multiplication):",
      suggested
    );
    if (topicName === null) {
      e.target.value = "";
      return;
    }
    setBusy(true);
    setGuide(null);
    setTopic(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("grade_level", grade);
      form.append("subject", "MATH");
      form.append("topic_name", topicName);
      const r = await api.pacingFromDocument(form);
      const d = await api.coachDashboard();
      setDash(d);
      await loadDocs(grade);
      await loadGuides(grade);
      setGuide(r.guide);
    } catch (err) {
      alert("Upload/generate failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function genFromDoc(id: string) {
    setBusy(true);
    setGuide(null);
    setTopic(null);
    try {
      const r = await api.generateGuideFromDoc(id);
      setGuide(r.guide);
      await loadGuides(grade);
    } catch (err) {
      alert("Generate failed: " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addDocToCalendar(id: string) {
    setBusy(true);
    try {
      const r = await api.calendarFromDocument(id);
      alert(
        `Read ${r.created} dated days from the pacing guide (${r.first} → ${r.last}). Open the 📅 Calendar to see them.`
      );
    } catch (err) {
      alert(
        "Couldn't read a dated schedule: " +
          (err as Error).message +
          "\n(The AI key must be on, and the guide must contain dates.)"
      );
    } finally {
      setBusy(false);
    }
  }

  async function clearTopics() {
    if (
      !confirm(
        `Clean slate for ${grade === "K" ? "Kindergarten" : `Grade ${grade}`}?\n\nThis deletes its topics, uploaded documents, calendar days, and saved guides. The roster and standards are kept. You'll re-upload this grade's pacing guide fresh.`
      )
    )
      return;
    try {
      const r = await api.clearTopics(grade);
      const d = await api.coachDashboard();
      setDash(d);
      setTopic(null);
      setGuide(null);
      await loadDocs(grade);
      await loadGuides(grade);
      alert(
        `Cleared: ${r.topics_deleted} topics, ${r.documents_deleted} documents, ${r.calendar_entries_deleted} calendar days, ${r.guides_deleted} saved guides.`
      );
    } catch (err) {
      alert("Clear failed: " + (err as Error).message);
    }
  }

  async function deleteDoc(id: string) {
    if (!confirm("Delete this document?")) return;
    try {
      await api.deleteDocument(id);
      await loadDocs(grade);
    } catch (err) {
      alert("Delete failed: " + (err as Error).message);
    }
  }

  async function reloadPacing() {
    setDocBusy("_reload");
    try {
      const r = await api.reloadPacing();
      const d = await api.coachDashboard();
      setDash(d);
      alert(
        `Pacing restored. ${r.topics_total} topics loaded (${r.pacing_added} added, standards synced).`
      );
    } catch (err) {
      alert("Restore failed: " + (err as Error).message);
    } finally {
      setDocBusy("");
    }
  }

  async function deleteTopic(id: string, name: string) {
    if (
      !confirm(
        `Delete the topic "${name}"? This removes the planning week (uploaded documents in its folder are kept).`
      )
    )
      return;
    try {
      await api.deletePacingTopic(id);
      const d = await api.coachDashboard();
      setDash(d);
      if (topic?.id === id) {
        setTopic(null);
        setGuide(null);
      }
    } catch (err) {
      alert("Delete failed: " + (err as Error).message);
    }
  }

  async function loadSummary() {
    try {
      setSummary(await api.schoolSummary());
    } catch {
      /* summary is best-effort */
    }
  }

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
        return api.coachDashboard();
      })
      .then((d) => {
        setDash(d);
        loadSummary();
        loadDocs(grade);
        loadGuides(grade);
      })
      .catch(() => router.push("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onRoster(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setRosterMsg("");
    try {
      const form = new FormData();
      form.append("file", file);
      const r = await api.importRoster(form);
      setRosterMsg(
        `Loaded ${r.students_created} new / ${r.students_updated} updated students · ` +
          `${r.teachers_created} teachers · ${r.classes_created} classes` +
          (r.error_count ? ` · ${r.error_count} row error(s)` : "")
      );
      loadSummary();
    } catch (err) {
      setRosterMsg("Import failed: " + (err as Error).message);
    } finally {
      setBusy(false);
      e.target.value = "";
    }
  }

  async function openWeek(id: string) {
    setGuide(null);
    setTopic(null);
    setBusy(true);
    try {
      setTopic(await api.pacingTopic(id));
    } catch (err) {
      alert("Could not open this topic: " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function makeGuide(id: string) {
    setBusy(true);
    try {
      const r = await api.generateGuide(id);
      setGuide(r.guide);
      await loadGuides(grade);
    } catch (err) {
      alert(
        "Generate failed: " +
          (err as Error).message +
          "\n\n(If this mentions a timeout, the AI took too long — try again, or use the '✨ Generate guide' on the uploaded document instead.)"
      );
    } finally {
      setBusy(false);
    }
  }

  if (!me || !dash) return <div className="p-10 text-gray-500">Loading…</div>;

  return (
    <main className="min-h-screen">
      <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🥑</span>
          <span className="font-bold text-avocado-dark">Avocado</span>
          <span className="text-gray-400">·</span>
          <span className="text-sm text-gray-600">
            {me.name} · <span className="capitalize">{me.role.replace("_", " ")}</span>
          </span>
          {build?.build && (
            <span
              title={`API version ${build.version} · build ${build.build}`}
              className="text-[10px] font-mono text-gray-400 border border-gray-200 rounded px-1.5 py-0.5"
            >
              build {build.build}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <a
            href="/calendar"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            📅 Calendar
          </a>
          <a
            href="/goal"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            🎯 Goal
          </a>
          <a
            href="/reports"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            📊 Reports
          </a>
          <a
            href="/assistant"
            className="text-sm font-semibold text-avocado-dark hover:underline"
          >
            🤖 AI Coach
          </a>
          <button
            onClick={() => {
              clearToken();
              router.push("/");
            }}
            className="text-sm text-gray-500 hover:text-gray-800"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="max-w-6xl mx-auto p-6">
        <h1 className="text-xl font-bold text-gray-800 mb-1">Collaborative Planning</h1>
        <p className="text-sm text-gray-500 mb-4">
          Pacing calendar · {dash.subjects.join(" / ")} · plan the week with your teachers
        </p>

        {/* School roster */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 mb-4 flex flex-wrap items-center gap-4">
          <div className="flex-1 min-w-[200px]">
            <div className="text-sm font-semibold text-gray-700">School Roster</div>
            {summary ? (
              <div className="text-xs text-gray-500 space-y-0.5">
                <div>
                  {summary.students} students · {summary.teachers} teachers ·{" "}
                  {summary.classes} classes
                  {summary.by_grade &&
                    Object.keys(summary.by_grade).length > 0 &&
                    " · by grade: " +
                      Object.entries(summary.by_grade)
                        .map(([g, n]) => `${g}=${n}`)
                        .join("  ")}
                </div>
                {(summary.ell != null || summary.ese != null) && (
                  <div className="text-gray-400">
                    {summary.ell ? `${summary.ell} ELL · ` : ""}
                    {summary.ese ? `${summary.ese} ESE · ` : ""}
                    {summary.fast_math_baseline
                      ? `${summary.fast_math_baseline} FAST Math baseline`
                      : ""}
                  </div>
                )}
              </div>
            ) : (
              <div className="text-xs text-gray-400">No roster loaded yet.</div>
            )}
          </div>
          <label className="inline-block bg-gray-800 hover:bg-black text-white text-sm font-semibold rounded-lg px-3 py-2 cursor-pointer">
            {busy ? "Working…" : "Upload Population CSV ⬆"}
            <input type="file" accept=".csv" onChange={onRoster} className="hidden" disabled={busy} />
          </label>
          {rosterMsg && (
            <div className="w-full text-xs text-gray-600">{rosterMsg}</div>
          )}
        </div>

        {/* Grade folders */}
        <div className="flex gap-2 mb-4">
          {GRADES.map((g) => {
            const count = dash.planning_weeks.filter(
              (w: any) => w.grade_level === g
            ).length;
            return (
              <button
                key={g}
                onClick={() => {
                  setGrade(g);
                  setTopic(null);
                  setGuide(null);
                  loadDocs(g);
                  loadGuides(g);
                }}
                className={`px-4 py-2 rounded-lg text-sm font-semibold border ${
                  grade === g
                    ? "bg-avocado text-white border-avocado"
                    : "bg-white text-gray-600 border-gray-200 hover:border-avocado"
                }`}
              >
                {g === "K" ? "Kindergarten" : `Grade ${g}`}
                <span className="ml-1 text-xs opacity-70">({count})</span>
              </button>
            );
          })}
        </div>

        {/* Primary flow: upload a topic's pacing guide → generate the guide */}
        <div className="bg-avocado-dark text-white rounded-xl p-4 mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="font-semibold">
              Upload {grade === "K" ? "Kindergarten" : `Grade ${grade}`} pacing guide → generate planning guide
            </div>
            <div className="text-xs opacity-80">
              Pick this grade's topic pacing guide (PDF, Word, or Excel). It creates
              the topic and writes the Collaborative Planning Guide from it.
            </div>
          </div>
          <label className="inline-block bg-white text-avocado-dark hover:bg-gray-100 text-sm font-bold rounded-lg px-4 py-2 cursor-pointer whitespace-nowrap">
            {busy ? "Working…" : "⬆ Upload pacing guide"}
            <input
              type="file"
              accept=".pdf,.docx,.xlsx,.xls,.txt,.csv"
              className="hidden"
              disabled={busy}
              onChange={uploadPacingAndGenerate}
            />
          </label>
        </div>

        {/* Document folders — organized by topic for this grade */}
        <div className="bg-white rounded-xl border border-gray-100 p-4 mb-6">
          <div className="text-sm font-semibold text-gray-700 mb-2">
            📁 {grade === "K" ? "Kindergarten" : `Grade ${grade}`} Documents
          </div>
          <div className="space-y-2">
            <DocFolder
              label="General — Year at a Glance & grade-wide files"
              files={docs["_grade"] || []}
              busy={docBusy === "_grade"}
              onUpload={(e) => uploadDoc(e, "")}
              onDelete={deleteDoc}
              onGenerate={genFromDoc}
                  onCalendar={addDocToCalendar}
            />
            {dash.planning_weeks
              .filter((w: any) => w.grade_level === grade)
              .map((w: any) => (
                <DocFolder
                  key={w.id}
                  label={`${w.topic_code} · ${w.name}`}
                  files={docs[w.topic_code] || []}
                  busy={docBusy === w.topic_code}
                  onUpload={(e) => uploadDoc(e, w.topic_code)}
                  onDelete={deleteDoc}
                  onGenerate={genFromDoc}
                  onCalendar={addDocToCalendar}
                />
              ))}
            {/* Folders for documents whose topic was deleted — kept, not lost */}
            {Object.keys(docs)
              .filter(
                (k) =>
                  k !== "_grade" &&
                  !dash.planning_weeks.some(
                    (w: any) => w.grade_level === grade && w.topic_code === k
                  )
              )
              .map((k) => (
                <DocFolder
                  key={k}
                  label={`${k} — documents (topic removed)`}
                  files={docs[k] || []}
                  busy={docBusy === k}
                  onUpload={(e) => uploadDoc(e, k)}
                  onDelete={deleteDoc}
                  onGenerate={genFromDoc}
                  onCalendar={addDocToCalendar}
                />
              ))}
          </div>
        </div>

        {/* Saved planning guides — persist across navigation */}
        {Object.keys(savedGuides).length > 0 && (
          <div className="bg-white rounded-xl border border-gray-100 p-4 mb-6">
            <div className="text-sm font-semibold text-gray-700 mb-2">
              💾 Saved Planning Guides — click to reopen
            </div>
            <ul className="divide-y divide-gray-50">
              {Object.values(savedGuides)
                .flat()
                .map((g: any) => (
                  <li
                    key={g.id}
                    className="flex items-center justify-between py-1.5 text-xs gap-2"
                  >
                    <button
                      onClick={() => openSavedGuide(g.id)}
                      className="text-avocado-dark hover:underline text-left truncate"
                      title={g.title}
                    >
                      📄 {g.title}
                      <span className="text-gray-400">
                        {" "}
                        · {g.ai_generated ? "AI" : "template"}
                        {g.created_at
                          ? " · " + new Date(g.created_at).toLocaleDateString()
                          : ""}
                      </span>
                    </button>
                    <button
                      onClick={() => removeSavedGuide(g.id)}
                      title="Delete saved guide"
                      className="text-gray-300 hover:text-red-500 shrink-0"
                    >
                      🗑
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-6">
          {/* Pacing calendar */}
          <div className="md:col-span-1">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold text-gray-700">
                {grade === "K" ? "Kindergarten" : `Grade ${grade}`} · Planning Weeks
              </h2>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowNew((v) => !v)}
                  className="text-xs font-semibold text-white bg-avocado hover:bg-avocado-dark rounded px-2 py-1"
                >
                  {showNew ? "Cancel" : "+ New Topic"}
                </button>
                <button
                  onClick={clearTopics}
                  title="Clean slate for this grade: delete its topics, documents, calendar, and guides"
                  className="text-xs text-red-500 hover:underline"
                >
                  Clear grade
                </button>
                <button
                  onClick={reloadPacing}
                  disabled={docBusy === "_reload"}
                  title="Restore the built-in sample pacing guides (Topic 1, 7) and standards/ALDs"
                  className="text-xs text-avocado-dark hover:underline disabled:opacity-50"
                >
                  {docBusy === "_reload" ? "Restoring…" : "↻ Restore samples"}
                </button>
              </div>
            </div>
            {showNew && (
              <NewTopicForm grade={grade} onCreate={createTopic} />
            )}
            <div className="space-y-2">
              {dash.planning_weeks.filter((w: any) => w.grade_level === grade)
                .length === 0 && (
                <div className="text-sm text-gray-500 bg-white border border-dashed border-gray-200 rounded-xl p-4 space-y-2">
                  <p>No pacing topics loaded for this grade yet.</p>
                  <button
                    onClick={reloadPacing}
                    disabled={docBusy === "_reload"}
                    className="bg-avocado hover:bg-avocado-dark text-white text-xs font-semibold rounded-lg px-3 py-2 disabled:opacity-60"
                  >
                    {docBusy === "_reload" ? "Restoring…" : "↻ Restore standard pacing guides"}
                  </button>
                </div>
              )}
              {dash.planning_weeks
                .filter((w: any) => w.grade_level === grade)
                .map((w: any) => (
                <div key={w.id} className="relative">
                  <button
                    onClick={() => openWeek(w.id)}
                    className={`w-full text-left bg-white rounded-xl border p-3 pr-8 transition ${
                      topic?.id === w.id
                        ? "border-avocado ring-1 ring-avocado"
                        : "border-gray-100 hover:border-avocado"
                    }`}
                  >
                    <div className="text-xs text-gray-400">
                      Grade {w.grade_level} · {w.subject} · {w.quarter}
                    </div>
                    <div className="font-semibold text-sm text-gray-800">
                      {w.topic_code} · {w.name}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                      🎯 {w.learning_target} · {w.benchmark_count} benchmarks
                    </div>
                  </button>
                  <button
                    onClick={() => deleteTopic(w.id, w.name)}
                    title="Delete topic"
                    className="absolute top-2 right-2 text-gray-300 hover:text-red-500"
                  >
                    🗑
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Selected week + guide */}
          <div className="md:col-span-2 space-y-4">
            {!topic && (
              <div className="bg-white rounded-xl border border-gray-100 p-8 text-center text-gray-400">
                Select a planning week to see the focus and build a Collaborative
                Planning Guide.
              </div>
            )}

            {topic && <TopicPanel topic={topic} busy={busy} onGuide={() => makeGuide(topic.id)} />}
            {guide && <GuideView guide={guide} />}
          </div>
        </div>
      </div>
    </main>
  );
}

function TopicPanel({ topic, busy, onGuide }: any) {
  const qf = topic.quick_facts || {};
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-bold text-gray-800">
            {topic.topic_code} · {topic.name}
          </h2>
          <p className="text-xs text-gray-500">
            Grade {topic.grade_level} {topic.subject} · {topic.quarter}
          </p>
          <p className="text-xs text-gray-400 mt-0.5">{topic.source}</p>
        </div>
        <button
          onClick={onGuide}
          disabled={busy}
          className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60 whitespace-nowrap"
        >
          {busy ? "Working…" : "Generate Planning Guide"}
        </button>
      </div>

      {/* Quick Facts */}
      <div className="mt-3 grid sm:grid-cols-2 gap-x-4 gap-y-1 text-xs bg-gray-50 rounded-lg p-3">
        <Fact label="Time Frame" value={qf.time_frame} />
        <Fact label="Assessment Date" value={qf.assessment_date} />
        <Fact label="ALD Focus" value={qf.ald_focus} />
        <Fact label="Topic Focus" value={qf.topic_focus} />
        <Fact label="Key Benchmarks" value={(qf.key_benchmarks || []).join(", ")} />
        <Fact label="MTR Practices" value={(qf.mtr_practices || []).join(" · ")} />
        <Fact label="Materials" value={(qf.materials || []).join(", ")} />
      </div>

      <div className="mt-3 text-sm">
        <div className="font-semibold text-gray-700">🎯 Learning Goal</div>
        <p className="text-gray-600">{topic.learning_target}</p>
      </div>

      {topic.lessons?.length > 0 && (
        <div className="mt-3 text-sm">
          <div className="font-semibold text-gray-700 mb-1">
            Lesson sequence ({topic.lessons.length})
          </div>
          <ol className="list-decimal ml-5 text-gray-600 space-y-0.5">
            {topic.lessons.map((L: any) => (
              <li key={L.code}>
                <span className="font-medium">{L.code}</span> {L.title}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}

function NewTopicForm({
  grade,
  onCreate,
}: {
  grade: string;
  onCreate: (p: any) => Promise<void>;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [quarter, setQuarter] = useState("");
  const [stds, setStds] = useState<any[]>([]);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .gradeStandards(grade)
      .then((r) => setStds(r.standards || []))
      .catch(() => setStds([]));
  }, [grade]);

  async function submit() {
    const benchmarks = Object.keys(picked).filter((k) => picked[k]);
    if (!code.trim() || !name.trim()) {
      alert("Enter a topic code and name.");
      return;
    }
    setBusy(true);
    try {
      await onCreate({
        topic_code: code,
        name,
        learning_target: target,
        quarter,
        benchmarks,
      });
    } catch (err) {
      alert("Create failed: " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="bg-white border border-avocado/40 rounded-xl p-3 mb-2 space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <input
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="Topic code (e.g. Topic 1)"
          className="border border-gray-200 rounded px-2 py-1 text-sm"
        />
        <input
          value={quarter}
          onChange={(e) => setQuarter(e.target.value)}
          placeholder="Quarter (e.g. First Nine Weeks)"
          className="border border-gray-200 rounded px-2 py-1 text-sm"
        />
      </div>
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Topic name (e.g. Understand Multiplication)"
        className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
      />
      <input
        value={target}
        onChange={(e) => setTarget(e.target.value)}
        placeholder="Learning target (I can…)"
        className="w-full border border-gray-200 rounded px-2 py-1 text-sm"
      />
      <div>
        <div className="text-xs font-semibold text-gray-600 mb-1">
          Benchmarks for this topic {stds.length === 0 && "(none loaded — click ↻ Restore samples to load standards)"}
        </div>
        <div className="max-h-40 overflow-y-auto border border-gray-100 rounded p-1 space-y-0.5">
          {stds.map((s) => (
            <label key={s.code} className="flex items-start gap-2 text-xs cursor-pointer">
              <input
                type="checkbox"
                checked={!!picked[s.code]}
                onChange={(e) =>
                  setPicked((p) => ({ ...p, [s.code]: e.target.checked }))
                }
                className="mt-0.5"
              />
              <span>
                <span className="font-medium">{s.code}</span>
                {s.has_ald && <span className="text-green-600"> ·ALD</span>}{" "}
                <span className="text-gray-500">{s.description}</span>
              </span>
            </label>
          ))}
        </div>
      </div>
      <button
        onClick={submit}
        disabled={busy}
        className="bg-avocado hover:bg-avocado-dark text-white text-sm font-semibold rounded-lg px-3 py-2 disabled:opacity-60"
      >
        {busy ? "Creating…" : "Create Topic"}
      </button>
    </div>
  );
}

function DocFolder({
  label,
  files,
  busy,
  onUpload,
  onDelete,
  onGenerate,
  onCalendar,
}: {
  label: string;
  files: any[];
  busy: boolean;
  onUpload: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onDelete: (id: string) => void;
  onGenerate?: (id: string) => void;
  onCalendar?: (id: string) => void;
}) {
  return (
    <div className="border border-gray-100 rounded-lg">
      <details open={files.length > 0}>
        <summary className="cursor-pointer px-3 py-2 flex items-center justify-between gap-2">
          <span className="text-sm text-gray-700">
            📂 {label}
            <span className="text-xs text-gray-400 ml-1">({files.length})</span>
          </span>
          <label className="text-xs bg-gray-800 hover:bg-black text-white rounded px-2 py-1 cursor-pointer whitespace-nowrap">
            {busy ? "Uploading…" : "Upload ⬆"}
            <input
              type="file"
              className="hidden"
              disabled={busy}
              onChange={onUpload}
            />
          </label>
        </summary>
        <div className="px-3 pb-2">
          {files.length === 0 ? (
            <p className="text-xs text-gray-400 py-1">
              No documents yet. Upload the pacing guide, bell ringer, resources…
            </p>
          ) : (
            <ul className="divide-y divide-gray-50">
              {files.map((f) => (
                <li
                  key={f.id}
                  className="flex items-center justify-between py-1.5 text-xs"
                >
                  <button
                    onClick={() => downloadDocument(f.id, f.filename)}
                    className="text-avocado-dark hover:underline truncate text-left"
                    title={f.name}
                  >
                    📄 {f.name}
                  </button>
                  <div className="flex items-center gap-2 shrink-0">
                    {onGenerate && (
                      <button
                        onClick={() => onGenerate(f.id)}
                        title="Generate a planning guide from this pacing document"
                        className="text-avocado-dark font-semibold hover:underline whitespace-nowrap"
                      >
                        ✨ Generate guide
                      </button>
                    )}
                    {onCalendar && (
                      <button
                        onClick={() => onCalendar(f.id)}
                        title="Read the dates & lessons from this pacing guide onto the calendar"
                        className="text-avocado-dark font-semibold hover:underline whitespace-nowrap"
                      >
                        📅 To calendar
                      </button>
                    )}
                    <span className="text-gray-300">
                      {Math.max(1, Math.round((f.size || 0) / 1024))} KB
                    </span>
                    <button
                      onClick={() => onDelete(f.id)}
                      title="Delete document"
                      className="text-gray-300 hover:text-red-500"
                    >
                      🗑
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="font-semibold text-gray-600">{label}: </span>
      <span className="text-gray-500">{value}</span>
    </div>
  );
}

function GuideView({ guide }: any) {
  return (
    <div className="bg-white rounded-xl border border-gray-100 p-5">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-bold text-gray-800">{guide.title}</h2>
        <button
          onClick={() => downloadGuideDocx(guide)}
          className="shrink-0 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg px-3 py-2"
        >
          ⬇ Download Word (.docx)
        </button>
      </div>
      <p className="text-xs text-gray-500 mb-1">
        {guide.ai_generated
          ? `AI-generated draft (${guide.generated_by})`
          : "Structured template draft"}{" "}
        — review with your team before teaching.
      </p>
      {!guide.ai_generated && guide.ai_status && (
        <p className="text-xs bg-yellow-50 border border-yellow-200 text-yellow-800 rounded px-2 py-1 mb-3">
          ⚠ {guide.ai_status}
        </p>
      )}

      {/* Topic-level clarifications & misconceptions */}
      {guide.benchmark_clarifications?.length > 0 && (
        <Section title="Benchmark Clarifications">
          {guide.benchmark_clarifications.map((c: any) => (
            <div key={c.code} className="mb-2">
              <div className="text-sm font-medium text-gray-800">{c.code}</div>
              <p className="text-xs text-gray-600">{c.description}</p>
              <ul className="list-disc ml-5 text-xs text-gray-600">
                {(c.clarifications || []).map((x: string, i: number) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          ))}
        </Section>
      )}

      {guide.common_misconceptions?.length > 0 && (
        <Section title="Common Misconceptions">
          <MisconceptionTable rows={guide.common_misconceptions} showCode />
        </Section>
      )}

      {/* Lessons */}
      <div className="mt-4 space-y-3">
        {(guide.lessons || []).map((L: any) => (
          <details
            key={L.code}
            className="border border-gray-100 rounded-lg p-3"
            open
          >
            <summary className="cursor-pointer font-semibold text-gray-800 text-sm">
              Lesson {L.code} — {L.title}
              <span className="text-xs text-gray-400 font-normal">
                {"  "}
                {(L.benchmarks || []).join(", ")}
              </span>
            </summary>
            <div className="mt-2 space-y-2 text-sm">
              <Line label="🎯 Learning Goal" value={L.learning_goal} />
              <List label="Success Criteria" items={L.success_criteria} />
              <Line label="Example" value={L.success_example} />
              <Line label="Benchmark Clarification" value={L.benchmark_clarification} />
              <Line label="Example" value={L.benchmark_example} />
              <Line label="Sentence Frame" value={L.sentence_frame} />
              {(L.vocabulary?.length > 0 || L.vocabulary_integration) && (
                <div className="rounded-lg border border-blue-100 bg-blue-50/50 p-2">
                  <div className="font-semibold text-gray-700 text-xs mb-0.5">
                    📚 Vocabulary (from the pacing guide)
                  </div>
                  {L.vocabulary?.length > 0 && (
                    <p className="text-xs text-gray-700">
                      {L.vocabulary.join(" · ")}
                    </p>
                  )}
                  {L.vocabulary_integration && (
                    <p className="text-xs text-gray-600 mt-0.5">
                      {L.vocabulary_integration}
                    </p>
                  )}
                </div>
              )}
              {L.misconceptions?.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-700 text-xs mb-1">
                    Common Misconceptions & Fixes
                  </div>
                  <MisconceptionTable rows={L.misconceptions} />
                </div>
              )}
              {(L.activate_prior_knowledge || L.i_do || L.we_do || L.explore_yall_do || L.you_do) ? (
                <div className="space-y-1">
                  <div className="font-semibold text-gray-700 text-xs">
                    Teaching Strategy — ACES Gradual Release (Scripted)
                  </div>
                  <Line label="Activate Prior Knowledge" value={L.activate_prior_knowledge} />
                  <Phase label="🅰 ASSEMBLE · I Do (Teacher Models)" phase={L.i_do} />
                  <Phase label="🅲 CONNECT · We Do (Guided Practice)" phase={L.we_do} />
                  <Phase label="🅴 EXPLORE · Y'all Do (Collaborative — pairs or groups of 4)" phase={L.explore_yall_do} />
                  <Phase label="🆂 SOLO · You Do (Independent Practice + CUBS)" phase={L.you_do} />
                  {L.cubs && typeof L.you_do !== "object" && (
                    <div className="rounded border border-amber-100 bg-amber-50/60 px-2 py-1 ml-4">
                      <span className="font-semibold text-gray-700 text-xs">
                        🦸 SOLO · Apply CUBS to the problem:{" "}
                      </span>
                      <span className="text-xs text-gray-700">{L.cubs}</span>
                    </div>
                  )}
                </div>
              ) : (
                <List label="Teaching Strategy (step-by-step)" items={L.teaching_strategy} ordered />
              )}
              {typeof L.i_do !== "object" &&
                L.cpa && (L.cpa.concrete || L.cpa.pictorial || L.cpa.abstract) && (
                <div className="grid sm:grid-cols-3 gap-2">
                  <CPA label="Concrete" value={L.cpa.concrete} />
                  <CPA label="Pictorial" value={L.cpa.pictorial} />
                  <CPA label="Abstract" value={L.cpa.abstract} />
                </div>
              )}
              {L.ald && (L.ald.level3 || L.ald.level2 || L.ald.level4) && (
                <div className="rounded-lg border border-avocado/40 bg-avocado/5 p-2">
                  <div className="font-semibold text-gray-700 text-xs mb-1">
                    Achievement Level Descriptors — what each level looks like
                  </div>
                  {L.ald.level2 && (
                    <p className="text-xs text-gray-500">
                      <span className="font-semibold">Level 2 (below):</span> {L.ald.level2}
                    </p>
                  )}
                  {L.ald.level3 && (
                    <p className="text-xs text-green-800 bg-green-50 rounded px-1 py-0.5">
                      <span className="font-semibold">⭐ Level 3 (ON GRADE — goal):</span> {L.ald.level3}
                    </p>
                  )}
                  {L.ald.level4 && (
                    <p className="text-xs text-gray-500">
                      <span className="font-semibold">Level 4 (above):</span> {L.ald.level4}
                    </p>
                  )}
                  {L.ald.level5 && (
                    <p className="text-xs text-gray-500">
                      <span className="font-semibold">Level 5 (mastery):</span> {L.ald.level5}
                    </p>
                  )}
                </div>
              )}
              {L.level3_look_like?.problem ? (
                <div className="rounded-lg border border-green-200 bg-green-50/60 p-2">
                  <div className="font-semibold text-green-800 text-xs mb-1">
                    ⭐ What a Level 3 (On-Grade) Looks Like — This Lesson
                  </div>
                  <Line label="Problem" value={L.level3_look_like.problem} />
                  <Line label="Worked solution" value={L.level3_look_like.solution} />
                  <Line
                    label="Student explanation"
                    value={L.level3_look_like.student_explanation}
                  />
                </div>
              ) : (
                <Line
                  label="⭐ Level 3 Proficiency Example (student voice)"
                  value={L.level3_example}
                />
              )}
              <List label="Checks for Understanding" items={L.cfu} />
              <Line
                label="🎫 Exit Ticket"
                value={
                  L.exit_ticket && typeof L.exit_ticket === "object"
                    ? `${L.exit_ticket.problem || ""}${
                        L.exit_ticket.answer ? `  →  ${L.exit_ticket.answer}` : ""
                      }`
                    : L.exit_ticket
                }
                highlight
              />
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

function Section({ title, children }: any) {
  return (
    <div className="mt-3 border-t border-gray-50 pt-3">
      <div className="font-semibold text-gray-700 text-sm mb-1">{title}</div>
      {children}
    </div>
  );
}

function Line({ label, value, highlight }: any) {
  if (!value) return null;
  return (
    <div className={highlight ? "bg-avocado-light rounded p-2" : ""}>
      <span className="font-semibold text-gray-700 text-xs">{label}: </span>
      <span className="text-gray-600 text-sm">{value}</span>
    </div>
  );
}

function List({ label, items, ordered }: any) {
  if (!items || items.length === 0) return null;
  const Tag = ordered ? "ol" : "ul";
  return (
    <div>
      <div className="font-semibold text-gray-700 text-xs">{label}</div>
      <Tag
        className={`${
          ordered ? "list-decimal" : "list-disc"
        } ml-5 text-gray-600 text-sm space-y-0.5`}
      >
        {items.map((x: string, i: number) => (
          <li key={i}>{x}</li>
        ))}
      </Tag>
    </div>
  );
}

function CPA({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-50 rounded p-2">
      <div className="text-xs font-semibold text-avocado-dark">{label}</div>
      <p className="text-xs text-gray-600 whitespace-pre-wrap">{value || "—"}</p>
    </div>
  );
}

// One fully-scripted ACES phase: problem, teacher script, teacher moves,
// Concrete/Pictorial/Abstract, CUBS (Solo), look-fors. Tolerates legacy strings.
function Phase({ label, phase }: { label: string; phase: any }) {
  if (!phase) return null;
  if (typeof phase === "string") return <Line label={label} value={phase} />;
  const say = phase.say ? (Array.isArray(phase.say) ? phase.say : [phase.say]) : [];
  return (
    <div className="rounded-lg border border-gray-100 bg-gray-50/60 p-2 ml-1">
      <div className="font-semibold text-avocado-dark text-xs mb-1">{label}</div>
      {phase.structure && <Line label="Collaborative structure" value={phase.structure} />}
      {phase.roles && <Line label="Each partner/group role" value={phase.roles} />}
      {phase.problem && <Line label="Problem worked" value={phase.problem} />}
      {say.length > 0 && (
        <div className="my-1">
          <div className="text-xs font-semibold text-gray-700">Teacher says:</div>
          <ul className="list-disc ml-5 text-sm text-gray-700 space-y-0.5">
            {say.map((s: string, i: number) => (
              <li key={i} className="italic">
                “{s}”
              </li>
            ))}
          </ul>
        </div>
      )}
      {phase.do && <Line label="Teacher does" value={phase.do} />}
      {(phase.concrete || phase.pictorial || phase.abstract) && (
        <div className="grid sm:grid-cols-3 gap-2 my-1">
          <CPA label="Concrete (manipulative)" value={phase.concrete} />
          <CPA label="Pictorial (drawing)" value={phase.pictorial} />
          <CPA label="Abstract (equation)" value={phase.abstract} />
        </div>
      )}
      {phase.cubs && (
        <div className="rounded border border-amber-100 bg-amber-50/60 px-2 py-1">
          <span className="font-semibold text-gray-700 text-xs">
            🦸 CUBS on this problem:{" "}
          </span>
          <span className="text-xs text-gray-700">{phase.cubs}</span>
        </div>
      )}
      {phase.look_for && <Line label="Look for" value={phase.look_for} />}
    </div>
  );
}

function MisconceptionTable({ rows, showCode }: { rows: any[]; showCode?: boolean }) {
  if (!rows?.length) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border border-gray-100">
        <thead>
          <tr className="bg-red-50 text-left text-gray-600">
            {showCode && <th className="p-1 font-semibold">Benchmark</th>}
            <th className="p-1 font-semibold">Misconception</th>
            <th className="p-1 font-semibold">Example Error</th>
            <th className="p-1 font-semibold">Correction Strategy</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m, i) => (
            <tr key={i} className="border-t border-gray-100 align-top">
              {showCode && (
                <td className="p-1 font-medium text-red-600 whitespace-nowrap">
                  {m.code}
                </td>
              )}
              <td className="p-1 text-gray-700">{m.misconception}</td>
              <td className="p-1 text-gray-500">{m.example || "—"}</td>
              <td className="p-1 text-gray-700">{m.fix || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

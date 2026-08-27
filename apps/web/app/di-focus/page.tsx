"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, getToken, openDiPacketHtml, downloadDiPacketPdf } from "@/lib/api";
import CoachHeader from "@/app/_components/CoachHeader";

const TIER_HEX: Record<string, string> = {
  Intensive: "#C0392B",
  Cusp: "#F1C40F",
  Strategic: "#2E86C1",
};

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
  const [packets, setPackets] = useState<any>(null);
  const [packetId, setPacketId] = useState("");
  const [packetBusy, setPacketBusy] = useState(false);

  async function generatePackets() {
    setPacketBusy(true);
    setPackets(null);
    try {
      const r = await api.createDiPackets(grade, standard, formId);
      setPacketId(r.packet_id);
      // Poll until ready (DI packet is one AI call, usually under a minute).
      for (let i = 0; i < 60; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const p = await api.getDiPackets(r.packet_id);
        if (p.status === "ready") {
          setPackets(p.content);
          break;
        }
        if (p.status === "error") {
          setErr(p.error || "DI packet generation failed.");
          break;
        }
      }
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setPacketBusy(false);
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

        {/* Generate full DI packets (Intensive / Cusp / Strategic) */}
        {s && (
          <div className="bg-white rounded-2xl border border-gray-100 p-5">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div>
                <div className="font-bold text-gray-800">
                  DI Packets — Intensive · Cusp · Strategic
                </div>
                <p className="text-xs text-gray-500 max-w-xl">
                  Full reteach per rotation tier, grounded in the B1G-M benchmark +
                  the most-missed questions, with the right number of teacher-led
                  (TLC) sessions per group and an OPM progress check.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={generatePackets}
                  disabled={packetBusy}
                  className="bg-avocado hover:bg-avocado-dark disabled:opacity-60 text-white text-sm font-semibold rounded-lg px-4 py-2"
                >
                  {packetBusy ? "Generating…" : packets ? "↻ Regenerate" : "✨ Generate DI packets"}
                </button>
                {packets && packetId && (
                  <>
                    <button
                      onClick={() =>
                        downloadDiPacketPdf(
                          packetId,
                          `DI-Packet-${standard}.pdf`
                        ).catch((e) => alert(String((e as Error).message)))
                      }
                      className="bg-avocado-dark text-white border border-avocado-dark text-sm font-semibold rounded-lg px-3 py-2"
                    >
                      ⬇ Download PDF
                    </button>
                    <button
                      onClick={() =>
                        openDiPacketHtml(packetId).catch((e) =>
                          alert("Couldn't open: " + (e as Error).message)
                        )
                      }
                      className="border border-avocado text-avocado-dark text-sm font-semibold rounded-lg px-3 py-2"
                    >
                      📄 Open / print
                    </button>
                  </>
                )}
              </div>
            </div>

            {packetBusy && (
              <p className="text-sm text-gray-400 mt-3">
                Writing the three packets from the benchmark and missed questions —
                about a minute…
              </p>
            )}

            {packets?.tiers?.length > 0 && (
              <>
                <div className="text-xs text-gray-500 mt-4">
                  Model: <b>{(packets.model || "").replace("_", " ")}</b> · click{" "}
                  <b>Open printable packet</b> for the full student pages with visuals.
                </div>
                <div className="grid md:grid-cols-3 gap-4 mt-2">
                  {packets.tiers.map((t: any) => (
                    <div
                      key={t.tier}
                      className="rounded-2xl border p-4"
                      style={{ borderTopColor: TIER_HEX[t.tier] || "#888", borderTopWidth: 4 }}
                    >
                      <div className="font-bold" style={{ color: TIER_HEX[t.tier] }}>
                        {t.tier} {"★".repeat(t.stars || 0)}
                      </div>
                      <div className="text-xs text-gray-500">
                        {t.band} · {t.student_count ?? 0} students ·{" "}
                        {(t.days || []).length} day
                        {(t.days || []).length === 1 ? "" : "s"}
                      </div>
                      {(t.days || []).map((d: any, i: number) => (
                        <div key={i} className="mt-2 text-xs text-gray-600">
                          <span className="font-semibold">Day {d.day}:</span> {d.title}
                          <span className="text-gray-400">
                            {" "}
                            · {(d.on_your_own || []).length} practice
                          </span>
                        </div>
                      ))}
                      <div className="text-xs text-gray-400 mt-2">
                        OPM check: {(t.opm || []).length} questions
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
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

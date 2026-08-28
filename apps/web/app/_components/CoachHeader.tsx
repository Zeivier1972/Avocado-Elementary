"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

type Leaf = { href: string; label: string };
type Group = { label: string; href?: string; children?: Leaf[] };

// Major tabs, with related pages grouped underneath. Keeps the top bar short
// and lets a coach find things by category instead of scanning 14 flat links.
const NAV: Group[] = [
  { label: "🏠 Home", href: "/home" },
  {
    label: "📊 Data & DI",
    children: [
      { href: "/assessments", label: "📝 Assessments" },
      { href: "/analysis", label: "📈 Analysis" },
      { href: "/reports", label: "📊 Reports" },
      { href: "/goal", label: "🎯 Goal" },
    ],
  },
  {
    label: "📚 Instruction",
    children: [
      { href: "/coach", label: "🗂 Planning" },
      { href: "/framework", label: "🧭 Framework" },
      { href: "/tier2", label: "🔤 Tier 2" },
    ],
  },
  {
    label: "👥 People",
    children: [
      { href: "/teachers", label: "👩‍🏫 Teachers" },
      { href: "/staff", label: "🧑‍🏫 Staff" },
    ],
  },
  {
    label: "📅 Calendar",
    children: [
      { href: "/schedule", label: "⏰ Schedule" },
      { href: "/calendar", label: "📅 Calendar" },
      { href: "/dates", label: "🗓 Key Dates" },
    ],
  },
  { label: "🤖 AI Coach", href: "/assistant" },
];

function isGroupActive(g: Group, active?: string) {
  if (!active) return false;
  if (g.href) return g.href === active;
  return !!g.children?.some((c) => c.href === active);
}

export default function CoachHeader({
  me,
  active,
  build,
}: {
  me?: any;
  active?: string;
  build?: any;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<string | null>(null); // open dropdown label
  const [mobile, setMobile] = useState(false); // mobile menu sheet
  const navRef = useRef<HTMLDivElement>(null);

  // Close any open menu when clicking outside the nav or pressing Escape.
  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpen(null);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(null);
        setMobile(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const signOut = () => {
    clearToken();
    router.push("/");
  };

  return (
    <header className="bg-white/95 backdrop-blur border-b border-gray-100 sticky top-0 z-30 shadow-[0_1px_3px_rgba(0,0,0,0.03)]">
      <div className="px-4 sm:px-6 py-2.5 flex items-center justify-between gap-3">
        {/* Brand */}
        <a href="/home" className="flex items-center gap-2 min-w-0 shrink-0">
          <span className="text-2xl leading-none">🥑</span>
          <span className="font-extrabold text-avocado-dark tracking-tight">
            Avocado
          </span>
          {me && (
            <span className="hidden md:inline text-sm text-gray-500 truncate max-w-[160px]">
              · {me.name}
            </span>
          )}
          {build?.build && (
            <span
              title={`API ${build.version} · build ${build.build}`}
              className="hidden lg:inline text-[10px] font-mono text-gray-400 border border-gray-200 rounded px-1.5 py-0.5"
            >
              {build.version || build.build}
            </span>
          )}
        </a>

        {/* Desktop nav */}
        <nav
          ref={navRef}
          className="hidden md:flex items-center gap-1"
          aria-label="Primary"
        >
          {NAV.map((g) => {
            const activeGroup = isGroupActive(g, active);
            const base =
              "flex items-center gap-1 rounded-lg px-3 py-2 text-sm font-semibold transition-colors";
            const tone = activeGroup
              ? "bg-avocado/10 text-avocado-dark"
              : "text-gray-600 hover:bg-gray-100 hover:text-avocado-dark";

            if (g.href) {
              return (
                <a key={g.label} href={g.href} className={`${base} ${tone}`}>
                  {g.label}
                </a>
              );
            }
            const isOpen = open === g.label;
            return (
              <div
                key={g.label}
                className="relative"
                onMouseEnter={() => setOpen(g.label)}
                onMouseLeave={() => setOpen(null)}
              >
                <button
                  type="button"
                  onClick={() => setOpen(isOpen ? null : g.label)}
                  aria-expanded={isOpen}
                  className={`${base} ${tone}`}
                >
                  {g.label}
                  <span
                    className={`text-[9px] mt-0.5 transition-transform ${
                      isOpen ? "rotate-180" : ""
                    }`}
                  >
                    ▼
                  </span>
                </button>
                {isOpen && (
                  <div className="absolute left-0 top-full pt-1 min-w-[210px] z-40">
                    <div className="rounded-xl border border-gray-100 bg-white shadow-lg p-1.5">
                      {g.children!.map((c) => {
                        const on = c.href === active;
                        return (
                          <a
                            key={c.href}
                            href={c.href}
                            className={`block rounded-lg px-3 py-2 text-sm ${
                              on
                                ? "bg-avocado/10 text-avocado-dark font-semibold"
                                : "text-gray-700 hover:bg-gray-50"
                            }`}
                          >
                            {c.label}
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
          <button
            onClick={signOut}
            className="ml-1 rounded-lg px-3 py-2 text-sm text-gray-400 hover:text-gray-700 hover:bg-gray-100"
          >
            Sign out
          </button>
        </nav>

        {/* Mobile toggle */}
        <button
          onClick={() => setMobile((v) => !v)}
          className="md:hidden rounded-lg border border-gray-200 px-3 py-2 text-sm font-semibold text-avocado-dark"
          aria-label="Menu"
          aria-expanded={mobile}
        >
          {mobile ? "✕ Close" : "☰ Menu"}
        </button>
      </div>

      {/* Mobile sheet */}
      {mobile && (
        <div className="md:hidden border-t border-gray-100 bg-white px-3 py-2 space-y-1 max-h-[70vh] overflow-y-auto">
          {NAV.map((g) =>
            g.href ? (
              <a
                key={g.label}
                href={g.href}
                className={`block rounded-lg px-3 py-2 text-sm font-semibold ${
                  isGroupActive(g, active)
                    ? "bg-avocado/10 text-avocado-dark"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                {g.label}
              </a>
            ) : (
              <div key={g.label} className="pt-1">
                <div className="px-3 pb-1 text-[11px] font-bold uppercase tracking-wide text-gray-400">
                  {g.label}
                </div>
                {g.children!.map((c) => (
                  <a
                    key={c.href}
                    href={c.href}
                    className={`block rounded-lg px-4 py-2 text-sm ${
                      c.href === active
                        ? "bg-avocado/10 text-avocado-dark font-semibold"
                        : "text-gray-700 hover:bg-gray-50"
                    }`}
                  >
                    {c.label}
                  </a>
                ))}
              </div>
            )
          )}
          <button
            onClick={signOut}
            className="block w-full text-left rounded-lg px-3 py-2 text-sm text-gray-500 hover:bg-gray-50"
          >
            Sign out
          </button>
        </div>
      )}
    </header>
  );
}

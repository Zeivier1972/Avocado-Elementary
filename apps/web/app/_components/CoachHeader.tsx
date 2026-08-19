"use client";

import { useRouter } from "next/navigation";
import { clearToken } from "@/lib/api";

const LINKS = [
  { href: "/home", label: "🏠 Home" },
  { href: "/teachers", label: "👩‍🏫 Teachers" },
  { href: "/coach", label: "🗂 Planning" },
  { href: "/framework", label: "🧭 Framework" },
  { href: "/schedule", label: "⏰ Schedule" },
  { href: "/staff", label: "🧑‍🏫 Staff" },
  { href: "/calendar", label: "📅 Calendar" },
  { href: "/dates", label: "🗓 Key Dates" },
  { href: "/reports", label: "📊 Reports" },
  { href: "/assessments", label: "📝 Assessments" },
  { href: "/analysis", label: "📈 Analysis" },
  { href: "/goal", label: "🎯 Goal" },
  { href: "/assistant", label: "🤖 AI Coach" },
];

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
  return (
    <header className="bg-white border-b border-gray-100 px-6 py-3 flex items-center justify-between sticky top-0 z-10">
      <div className="flex items-center gap-2 min-w-0">
        <span className="text-2xl">🥑</span>
        <span className="font-bold text-avocado-dark">Avocado</span>
        {me && (
          <>
            <span className="text-gray-300">·</span>
            <span className="text-sm text-gray-600 truncate">
              {me.name}
            </span>
          </>
        )}
        {build?.build && (
          <span
            title={`API ${build.version} · build ${build.build}`}
            className="hidden sm:inline text-[10px] font-mono text-gray-400 border border-gray-200 rounded px-1.5 py-0.5"
          >
            build {build.build}
          </span>
        )}
      </div>
      <nav className="flex items-center gap-3 flex-wrap justify-end">
        {LINKS.map((l) => (
          <a
            key={l.href}
            href={l.href}
            className={`text-sm ${
              active === l.href
                ? "font-bold text-avocado-dark underline"
                : "font-semibold text-avocado-dark hover:underline"
            }`}
          >
            {l.label}
          </a>
        ))}
        <button
          onClick={() => {
            clearToken();
            router.push("/");
          }}
          className="text-sm text-gray-500 hover:text-gray-800"
        >
          Sign out
        </button>
      </nav>
    </header>
  );
}

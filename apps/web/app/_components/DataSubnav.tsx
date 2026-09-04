"use client";

// A linked strip tying the analytics cluster together so the coach can jump
// between related data views in one click, keeping the same grade in context.
const LINKS = [
  { href: "/reports", label: "📊 Reports", hint: "FAST · i-Ready · Topic, per class & student" },
  { href: "/assessments", label: "📝 Assessments", hint: "Topic tests, standards, results & most-missed" },
  { href: "/analysis", label: "📈 Analysis", hint: "Goal rubric, projections, color codes" },
  { href: "/goal", label: "🎯 Goal", hint: "School goal & progress" },
];

export default function DataSubnav({ active }: { active: string }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-4 rounded-2xl border border-gray-100 bg-white/70 backdrop-blur px-2 py-1.5">
      <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wide px-2">
        📊 Data &amp; DI
      </span>
      {LINKS.map((l) => {
        const on = active === l.href;
        return (
          <a
            key={l.href}
            href={l.href}
            title={l.hint}
            className={`text-sm font-semibold rounded-lg px-3 py-1.5 transition-colors ${
              on
                ? "bg-avocado text-white shadow-sm"
                : "text-gray-600 hover:bg-avocado/10 hover:text-avocado-dark"
            }`}
          >
            {l.label}
          </a>
        );
      })}
      <span className="hidden sm:inline text-xs text-gray-400 ml-auto pr-2">
        same grade follows you across these
      </span>
    </div>
  );
}

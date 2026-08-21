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
    <div className="flex flex-wrap items-center gap-2 mb-4">
      <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide mr-1">
        Data:
      </span>
      {LINKS.map((l) => {
        const on = active === l.href;
        return (
          <a
            key={l.href}
            href={l.href}
            title={l.hint}
            className={`text-sm font-semibold rounded-full px-3 py-1 border ${
              on
                ? "bg-avocado text-white border-avocado"
                : "bg-white text-avocado-dark border-gray-200 hover:bg-avocado/5"
            }`}
          >
            {l.label}
          </a>
        );
      })}
      <span className="text-xs text-gray-400 ml-1">
        · same grade follows you across these
      </span>
    </div>
  );
}

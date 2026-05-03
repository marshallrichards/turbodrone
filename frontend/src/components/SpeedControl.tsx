import type { SpeedTier } from "../hooks/useControls";

interface SpeedControlProps {
  enabled: boolean;
  value: SpeedTier;
  onChange: (tier: SpeedTier) => void;
}

const TIERS: { value: SpeedTier; label: string; help: string }[] = [
  { value: 0, label: "Low",  help: "Slow / beginner stick scaling" },
  { value: 1, label: "Med",  help: "Medium stick scaling" },
  { value: 2, label: "High", help: "Full stick range" },
];

export default function SpeedControl({ enabled, value, onChange }: SpeedControlProps) {
  const baseSegment =
    "px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition-colors duration-150 ease-in-out focus:outline-none";
  const disabledTitle = "Speed control is unavailable for this implementation";

  return (
    <div
      className={`flex items-center gap-2 bg-gray-900/70 backdrop-blur-md border border-gray-700/80 rounded-lg shadow-md px-3 py-2 ${
        enabled ? "" : "opacity-60"
      }`}
      title={enabled ? "Adjust drone control sensitivity" : disabledTitle}
    >
      <span className="text-[10px] tracking-[0.18em] uppercase text-gray-300 select-none">
        Speed
      </span>
      <div className="inline-flex rounded-md border border-gray-600/70 overflow-hidden">
        {TIERS.map((tier, idx) => {
          const active = enabled && value === tier.value;
          const segmentClasses = active
            ? "bg-blue-600 text-white"
            : enabled
              ? "bg-gray-800/80 text-gray-200 hover:bg-gray-700/80"
              : "bg-gray-800/60 text-gray-400 cursor-not-allowed";
          const borderClasses = idx > 0 ? "border-l border-gray-600/70" : "";
          return (
            <button
              key={tier.value}
              type="button"
              disabled={!enabled}
              onClick={() => enabled && onChange(tier.value)}
              className={`${baseSegment} ${segmentClasses} ${borderClasses}`}
              title={enabled ? tier.help : disabledTitle}
              aria-pressed={active}
            >
              {tier.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

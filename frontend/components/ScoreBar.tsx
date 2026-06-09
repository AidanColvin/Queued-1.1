// A thin amber fill bar representing the match score — no number, by design.

interface ScoreBarProps {
  score: number; // 0..1
}

export default function ScoreBar({ score }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  return (
    <div className="flex items-center gap-2">
      <span className="shrink-0 text-[10px] font-semibold uppercase tracking-[0.18em] text-amber/70">
        Match
      </span>
      <div
        className="h-1 w-full overflow-hidden rounded-full bg-white/10"
        role="meter"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Match score"
      >
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber/70 to-amber shadow-[0_0_8px_rgba(245,166,35,0.6)] transition-[width] duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

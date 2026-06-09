// A thin amber fill bar representing the match score — no number, by design.

interface ScoreBarProps {
  score: number; // 0..1
}

export default function ScoreBar({ score }: ScoreBarProps) {
  const pct = Math.max(0, Math.min(1, score)) * 100;
  return (
    <div
      className="h-[3px] w-full overflow-hidden rounded-full bg-white/25"
      role="meter"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label="Match score"
    >
      <div className="h-full rounded-full bg-white transition-[width] duration-500" style={{ width: `${pct}%` }} />
    </div>
  );
}

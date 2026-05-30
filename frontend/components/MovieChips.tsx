'use client';

interface MovieChipsProps {
  titles: string[];
  onRemove: (title: string) => void;
}

/** Removable chips for the currently-selected seed titles. */
export default function MovieChips({ titles, onRemove }: MovieChipsProps) {
  if (titles.length === 0) return null;
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {titles.map((title) => (
        <span
          key={title}
          className="inline-flex items-center gap-2 rounded-full border border-warm bg-surface px-3 py-1.5 text-sm text-ink"
        >
          {title}
          <button
            type="button"
            onClick={() => onRemove(title)}
            aria-label={`Remove ${title}`}
            className="text-muted transition hover:text-pass"
          >
            ✕
          </button>
        </span>
      ))}
    </div>
  );
}

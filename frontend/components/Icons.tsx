// A small set of crisp, stroke-based SVG icons (24×24, currentColor) used across
// the deck UI in place of emoji/text glyphs. Keeping them inline avoids a runtime
// icon dependency and lets each icon inherit color + size from its button.

interface IconProps {
  className?: string;
  /** Render the glyph filled instead of stroked (e.g. an active heart). */
  filled?: boolean;
}

const base = 'h-6 w-6';

function Svg({ className, children, filled }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className ?? base}
    >
      {children}
    </svg>
  );
}

export function HeartIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M20.8 5.6a5.5 5.5 0 0 0-7.8 0L12 6.6l-1-1a5.5 5.5 0 0 0-7.8 7.8l1 1 7.8 7.8 7.8-7.8 1-1a5.5 5.5 0 0 0 0-7.8z" />
    </Svg>
  );
}

export function XIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </Svg>
  );
}

export function BookmarkIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </Svg>
  );
}

export function EyeOffIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9.9 4.2A9.1 9.1 0 0 1 12 4c5 0 9.3 3.2 11 8a12.4 12.4 0 0 1-2.2 3.4M6.6 6.6A12.5 12.5 0 0 0 1 12c1.7 4.8 6 8 11 8 1.9 0 3.7-.4 5.3-1.2M3 3l18 18" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </Svg>
  );
}

export function PlayIcon(props: IconProps) {
  return (
    <Svg {...props} filled>
      <path d="M6 4.5v15l13-7.5z" />
    </Svg>
  );
}

export function UndoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 14 4 9l5-5" />
      <path d="M4 9h11a5 5 0 0 1 0 10h-1" />
    </Svg>
  );
}

export function InfoIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 16v-4M12 8h.01" />
    </Svg>
  );
}

export function StarIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6-5.4-2.8L6.6 22l1-6L3.2 9.7l6.1-.9z" />
    </Svg>
  );
}

export function FilmIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M3 15h18M8 4v16M16 4v16" />
    </Svg>
  );
}

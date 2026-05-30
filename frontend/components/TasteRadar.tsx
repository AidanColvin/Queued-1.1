'use client';

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from 'recharts';

import type { Recommendation } from '@/lib/types';

interface TasteRadarProps {
  liked: Recommendation[];
}

// Six canonical genre axes for the taste fingerprint.
const AXES = ['Drama', 'Thriller', 'Comedy', 'Sci-Fi', 'Action', 'Documentary'];

/** Radar chart of liked-card genre distribution across six axes. */
export default function TasteRadar({ liked }: TasteRadarProps) {
  const counts = AXES.map((axis) => ({
    axis,
    value: liked.filter((r) => r.genres.includes(axis)).length,
  }));
  const max = Math.max(1, ...counts.map((c) => c.value));

  return (
    <div className="h-56 w-full" aria-label="Taste fingerprint radar chart">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={counts} outerRadius="72%">
          <PolarGrid stroke="rgba(245,243,238,0.12)" />
          <PolarAngleAxis dataKey="axis" tick={{ fill: '#9aa0a6', fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, max]} tick={false} axisLine={false} />
          <Radar dataKey="value" stroke="#f5a623" fill="#f5a623" fillOpacity={0.35} dot />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

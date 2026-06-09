'use client';

import { useSearchParams } from 'next/navigation';
import { Suspense, useMemo } from 'react';

import DeckExperience from '@/components/DeckExperience';
import { decodeTitles } from '@/lib/util';

function ResultsInner() {
  const params = useSearchParams();
  const titles = useMemo(() => decodeTitles(params), [params]);
  return <DeckExperience seedTitles={titles} />;
}

// Shareable deck: /results?titles=[...] seeds the deck with specific titles.
export default function ResultsPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-slate">Loading…</div>}>
      <ResultsInner />
    </Suspense>
  );
}

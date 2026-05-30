'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import MovieChips from '@/components/MovieChips';
import SearchInput from '@/components/SearchInput';
import type { SearchResult } from '@/lib/types';
import { encodeTitles } from '@/lib/util';

export default function HomePage() {
  const router = useRouter();
  const [titles, setTitles] = useState<string[]>([]);

  function addTitle(result: SearchResult) {
    setTitles((prev) => (prev.includes(result.title) ? prev : [...prev, result.title]));
  }

  function removeTitle(title: string) {
    setTitles((prev) => prev.filter((t) => t !== title));
  }

  function findWatches() {
    if (titles.length === 0) return;
    router.push(`/results?${encodeTitles(titles)}`);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-8 px-5 py-16">
      <div className="text-center">
        <p className="mb-3 text-sm uppercase tracking-[0.3em] text-amber/80">NextWatch</p>
        <h1 className="font-serif text-5xl leading-tight text-ink sm:text-6xl">What have you loved?</h1>
        <p className="mt-4 text-muted">
          Name a few films or shows. We&apos;ll build you a deck to swipe through — and learn your taste as you go.
        </p>
      </div>

      <div className="w-full">
        <SearchInput onSelect={addTitle} selectedTitles={titles} />
      </div>

      <MovieChips titles={titles} onRemove={removeTitle} />

      <button
        type="button"
        onClick={findWatches}
        disabled={titles.length === 0}
        className="rounded-full bg-amber px-8 py-4 text-lg font-medium text-charcoal transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-40"
      >
        Find my next watch →
      </button>

      {titles.length === 0 && (
        <p className="text-sm text-muted/70">Try: The Wire · Severance · Parasite</p>
      )}
    </main>
  );
}

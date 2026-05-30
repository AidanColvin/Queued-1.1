'use client';

import { useEffect, useId, useRef, useState } from 'react';

import { searchTitles } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

interface SearchInputProps {
  onSelect: (result: SearchResult) => void;
  selectedTitles: string[];
}

const DEBOUNCE_MS = 220;

export default function SearchInput({ onSelect, selectedTitles }: SearchInputProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const listId = useId();
  const selected = new Set(selectedTitles.map((t) => t.toLowerCase()));

  // Debounced search with in-flight cancellation.
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setOpen(false);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchTitles(q, 'all', controller.signal);
        setResults(res);
        setActive(0);
        setOpen(true);
      } catch {
        /* aborted or network error — leave previous results */
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [query]);

  function choose(result: SearchResult) {
    if (selected.has(result.title.toLowerCase())) return;
    onSelect(result);
    setQuery('');
    setResults([]);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || results.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActive((a) => (a + 1) % results.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (a - 1 + results.length) % results.length);
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const r = results[active];
      if (r) choose(r);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  }

  return (
    <div className="relative w-full">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
        onFocus={() => results.length && setOpen(true)}
        placeholder="Search a film or show you loved…"
        role="combobox"
        aria-label="Search titles"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        className="w-full rounded-xl border border-warm bg-surface/80 px-4 py-3.5 text-lg text-ink outline-none transition placeholder:text-muted/70 focus:border-amber"
      />
      {open && results.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-40 mt-2 max-h-72 w-full overflow-auto rounded-xl border border-warm bg-surface-2 py-1 shadow-2xl"
        >
          {results.map((r, i) => {
            const taken = selected.has(r.title.toLowerCase());
            return (
              <li
                key={`${r.tmdb_id ?? r.title}-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseEnter={() => setActive(i)}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(r);
                }}
                className={`flex cursor-pointer items-center justify-between px-4 py-2.5 text-ink ${
                  i === active ? 'bg-white/5' : ''
                } ${taken ? 'opacity-40' : ''}`}
              >
                <span className="truncate">
                  {r.title}
                  {r.year ? <span className="text-muted"> ({r.year})</span> : null}
                </span>
                <span className="ml-3 shrink-0 text-[11px] uppercase tracking-wide text-muted">
                  {r.type === 'tv' ? 'TV' : 'Film'}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {loading && query.trim() && (
        <span className="absolute right-4 top-4 text-sm text-muted">…</span>
      )}
    </div>
  );
}

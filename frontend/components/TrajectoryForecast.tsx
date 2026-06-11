'use client';

import { useState, useEffect } from 'react';

export default function TrajectoryForecast() {
  const [forecast, setForecast] = useState({ loves: [], hates: [], loading: true });

  useEffect(() => {
    const fetchForecast = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/predict/crystal-ball`);
        const data = await res.json();
        setForecast({ loves: data.loves, hates: data.hates, loading: false });
      } catch (error) {
        console.error("Crystal Ball API error:", error);
        setForecast({ loves: [], hates: [], loading: false });
      }
    };
    fetchForecast();
  }, []);

  if (forecast.loading) {
    return <div className="animate-pulse h-32 bg-gray-800/50 rounded-2xl my-8"></div>;
  }

  return (
    <div className="p-6 bg-black/40 backdrop-blur-md rounded-3xl border border-gray-800/50 text-white my-8">
      <h3 className="text-xl font-medium mb-4 tracking-tight">The Crystal Ball 🔮</h3>
      <p className="text-sm text-gray-400 mb-6">Based on your recent swipes, the engine predicts your future trajectory.</p>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-emerald-900/20 p-4 rounded-2xl border border-emerald-800/30">
          <h4 className="text-emerald-400 text-sm font-semibold mb-3">DESTINED TO LOVE</h4>
          {forecast.loves.map((movie: any) => (
            <div key={movie.id} className="flex justify-between items-center mb-2">
              <span className="text-sm">{movie.title}</span>
              <span className="text-xs text-emerald-500 bg-emerald-950 px-2 py-1 rounded-full">
                {(movie.score * 100).toFixed(0)}% Match
              </span>
            </div>
          ))}
        </div>

        <div className="bg-rose-900/20 p-4 rounded-2xl border border-rose-800/30">
          <h4 className="text-rose-400 text-sm font-semibold mb-3">DESTINED TO SKIP</h4>
          {forecast.hates.map((movie: any) => (
            <div key={movie.id} className="flex justify-between items-center mb-2">
              <span className="text-sm">{movie.title}</span>
              <span className="text-xs text-rose-500 bg-rose-950 px-2 py-1 rounded-full">
                Hate Probability High
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

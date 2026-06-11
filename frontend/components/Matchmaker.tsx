'use client';

import { useState } from 'react';

// Takes: API URL and user inputs.
// Does: Fetches cosine similarity vector scores between two session profiles.
// Returns: A text-light, glass-morphism React component displaying the match percentage.

export default function Matchmaker() {
  const [userA, setUserA] = useState('');
  const [userB, setUserB] = useState('');
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const checkMatch = async () => {
    if (!userA || !userB) return;
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/social/match?user_a=${userA}&user_b=${userB}`);
      if (res.ok) {
        const data = await res.json();
        setResult(data);
      } else {
        setResult({ error: "Profiles not found or need more swipes." });
      }
    } catch (e) {
      console.error(e);
      setResult({ error: "Network error. Is the backend running?" });
    }
    setLoading(false);
  };

  return (
    <div className="p-6 bg-black/40 backdrop-blur-md rounded-3xl border border-gray-800/50 text-white my-8 w-full">
      <h3 className="text-xl font-medium mb-4 tracking-tight">Taste Matchmaker 🧬</h3>
      <p className="text-sm text-gray-400 mb-6">Compare your cinematic footprint with a friend.</p>
      
      <div className="space-y-3 mb-6 flex flex-col md:flex-row md:space-y-0 md:space-x-3">
        <input 
          type="text" 
          placeholder="Your Session ID" 
          className="w-full bg-gray-900/50 border border-gray-700 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-indigo-500" 
          value={userA} 
          onChange={(e) => setUserA(e.target.value)} 
        />
        <input 
          type="text" 
          placeholder="Friend's Session ID" 
          className="w-full bg-gray-900/50 border border-gray-700 rounded-xl px-4 py-2 text-sm focus:outline-none focus:border-indigo-500" 
          value={userB} 
          onChange={(e) => setUserB(e.target.value)} 
        />
      </div>
      
      <button 
        onClick={checkMatch} 
        className="w-full bg-white text-black font-medium py-2 rounded-xl text-sm hover:bg-gray-200 transition-colors"
      >
        {loading ? 'Scanning Vectors...' : 'Calculate Compatibility'}
      </button>

      {result && !result.error && (
        <div className="mt-6 text-center p-4 bg-gray-900/50 rounded-2xl border border-gray-800">
          <p className="text-sm text-gray-400 mb-1">Match Rate</p>
          <p className="text-5xl font-semibold bg-gradient-to-r from-indigo-400 to-purple-400 bg-clip-text text-transparent">
            {result.match_percentage}%
          </p>
        </div>
      )}

      {result && result.error && (
        <div className="mt-4 text-center p-3 bg-rose-900/20 text-rose-400 rounded-xl border border-rose-800/30 text-sm">
          {result.error}
        </div>
      )}
    </div>
  );
}

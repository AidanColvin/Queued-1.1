"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL, fetchHealth, fetchDemoRecommendations, runTraining } from "@/lib/api";

export default function ApiTestPage() {
  const [health, setHealth] = useState<any>(null);
  const [recs, setRecs] = useState<any>(null);
  const [train, setTrain] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setHealth(await fetchHealth());
        setRecs(await fetchDemoRecommendations());
      } catch (e: any) {
        setErr(e?.message || "Unknown error");
      }
    })();
  }, []);

  return (
    <main style={{ padding: 24, fontFamily: "Arial, sans-serif" }}>
      <h1>NextWatch connection test</h1>
      <p>API base URL: {API_BASE_URL}</p>

      <button
        onClick={async () => {
          try {
            setTrain(await runTraining());
          } catch (e: any) {
            setErr(e?.message || "Training error");
          }
        }}
        style={{ padding: "10px 14px", marginBottom: 16 }}
      >
        Run training test
      </button>

      {err ? <pre style={{ color: "crimson" }}>{err}</pre> : null}
      <h2>Health</h2>
      <pre>{JSON.stringify(health, null, 2)}</pre>
      <h2>Recommendations</h2>
      <pre>{JSON.stringify(recs, null, 2)}</pre>
      <h2>Training</h2>
      <pre>{JSON.stringify(train, null, 2)}</pre>
    </main>
  );
}

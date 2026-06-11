export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE_URL}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Health failed: ${res.status}`);
  return res.json();
}

export async function fetchDemoRecommendations() {
  const res = await fetch(`${API_BASE_URL}/api/recommendations/demo`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Recommendations failed: ${res.status}`);
  return res.json();
}

export async function runTraining() {
  const res = await fetch(`${API_BASE_URL}/api/train`, {
    method: "POST",
    headers: { "Content-Type": "application/json" }
  });
  if (!res.ok) throw new Error(`Training failed: ${res.status}`);
  return res.json();
}

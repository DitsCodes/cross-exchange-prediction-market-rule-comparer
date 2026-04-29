import type { CompareResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export async function createCompare(url: string): Promise<{ comparison_id: string }> {
  const resp = await fetch(`${API_BASE}/api/v1/compare`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
  });
  if (!resp.ok) {
    throw new Error(`compare failed (${resp.status}): ${await resp.text()}`);
  }
  return resp.json();
}

export async function getCompare(id: string): Promise<CompareResult> {
  const resp = await fetch(`${API_BASE}/api/v1/compare/${id}`, {
    cache: "no-store",
  });
  if (!resp.ok) {
    throw new Error(`fetch compare failed (${resp.status})`);
  }
  return resp.json();
}

export function streamCompareUrl(id: string): string {
  return `${API_BASE}/api/v1/compare/${id}/stream`;
}

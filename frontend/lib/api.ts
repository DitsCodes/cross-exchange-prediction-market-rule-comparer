import type { CompareResult } from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

function unwrapNetworkError(error: unknown): never {
  if (
    error instanceof TypeError ||
    (error instanceof Error &&
      /failed to fetch|networkerror|load failed|terminated/i.test(error.message))
  ) {
    throw new Error(
      `Cannot reach the RuleC API at ${API_BASE}. Start the backend and Postgres (` +
        `e.g. \`docker compose up\` from the repo root), or run \`uvicorn\` locally. ` +
        `If the API is elsewhere, set NEXT_PUBLIC_API_BASE in frontend/.env.local and restart Next.js.`
    );
  }
  throw error;
}

export async function createCompare(url: string): Promise<{ comparison_id: string }> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/compare`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (!resp.ok) {
      throw new Error(`compare failed (${resp.status}): ${await resp.text()}`);
    }
    return resp.json();
  } catch (e) {
    unwrapNetworkError(e);
  }
}

export async function getCompare(id: string): Promise<CompareResult> {
  try {
    const resp = await fetch(`${API_BASE}/api/v1/compare/${id}`, {
      cache: "no-store",
    });
    if (!resp.ok) {
      throw new Error(`fetch compare failed (${resp.status})`);
    }
    return resp.json();
  } catch (e) {
    unwrapNetworkError(e);
  }
}

export function streamCompareUrl(id: string): string {
  return `${API_BASE}/api/v1/compare/${id}/stream`;
}

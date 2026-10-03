// Calls Linq's Partner API (v3) for scout's line. The bridge's Linq platform
// (linq.ts) and the demo group commands (demo/) both go through it.

export const LINQ_API_URL = "https://api.linqapp.com/api/partner/v3";

// The real API unless a test stands in for it.
export type LinqApi = { apiKey: string; apiUrl: string };

// One member of a chat, scout's own number included.
export type LinqHandle = { handle: string; is_me: boolean; status: string };

// Says which call failed and how, so a caller can tell "not found" from an outage.
export class LinqApiError extends Error {
  constructor(
    readonly path: string,
    readonly status: number,
    responseText: string,
  ) {
    super(`Linq ${path} returned ${status}: ${responseText}`);
  }
}

// A GET, or a POST when there is a body, unless the request names its method.
export async function callLinq(
  api: LinqApi,
  path: string,
  request: { method?: string; body?: object } = {},
): Promise<unknown> {
  const response = await fetch(`${api.apiUrl}${path}`, {
    method: request.method ?? (request.body ? "POST" : "GET"),
    headers: { Authorization: `Bearer ${api.apiKey}`, "Content-Type": "application/json" },
    body: request.body ? JSON.stringify(request.body) : undefined,
  });
  if (!response.ok) {
    throw new LinqApiError(path, response.status, await response.text());
  }
  // Some calls, such as sharing a contact card, answer with no body.
  const text = await response.text();
  return text ? JSON.parse(text) : null;
}

// The scout service's developer endpoints: start a chat's trip partway
// through the journey, show it, or reset it (src/scout/dev_endpoints.py).

import { scoutUrl } from "../scout";

export const SEED_STAGES = ["poll-open", "destination-chosen"] as const;
export type SeedStage = (typeof SEED_STAGES)[number];

// The parts of a trip the console prints. showTrip returns all of it.
export type TripSummary = {
  destination: string | null;
  dates: { start: string; end: string } | null;
  open_poll: { options: { name: string; estimated_cost_per_person_usd: number }[] } | null;
};

export async function seedTrip(
  chatId: string,
  stage: SeedStage,
  members: { phone: string; name: string }[],
): Promise<TripSummary> {
  const trip = await callDevEndpoint("POST", `${tripPath(chatId)}/seed`, { stage, members });
  return trip as TripSummary;
}

export function showTrip(chatId: string): Promise<unknown> {
  return callDevEndpoint("GET", tripPath(chatId));
}

export async function resetTrip(chatId: string): Promise<void> {
  await callDevEndpoint("DELETE", tripPath(chatId));
}

function tripPath(chatId: string): string {
  return `/dev/trips/${encodeURIComponent(chatId)}`;
}

async function callDevEndpoint(method: string, path: string, body?: object): Promise<unknown> {
  const response = await fetch(`${scoutUrl()}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`scout ${method} ${path} returned ${response.status}: ${await response.text()}`);
  }
  return response.status === 204 ? null : response.json();
}

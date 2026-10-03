// The scout service's developer endpoints: start a chat's trip partway
// through the journey, show it or its latest messages, or reset it
// (src/scout/dev_endpoints.py).

import { scoutUrl } from "../scout";

export const SEED_STAGES = ["poll-open", "destination-chosen"] as const;
export type SeedStage = (typeof SEED_STAGES)[number];

// One message from the chat log. A sender of null is scout.
export type LoggedMessage = { sender_phone: string | null; text: string };

export async function seedTrip(
  chatId: string,
  stage: SeedStage,
  members: { phone: string; name: string }[],
): Promise<void> {
  await callDevEndpoint("POST", `${tripPath(chatId)}/seed`, { stage, members });
}

export async function showMessages(chatId: string): Promise<LoggedMessage[]> {
  return (await callDevEndpoint("GET", `${tripPath(chatId)}/messages`)) as LoggedMessage[];
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

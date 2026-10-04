// How the bridge hands a text to scout's Python service and gets back what to
// send.

import type { Tapback } from "./tapbacks";

const DEFAULT_SCOUT_URL = "http://127.0.0.1:8787";

// A photo (image/...) or voice note (audio/...), exactly as it was sent, like
// an iPhone's image/heic or audio/x-caf. scout keeps and converts it.
export type IncomingAttachment = {
  media_type: string;
  base64_data: string;
};

export type IncomingText = {
  space_id: string;
  sender_phone: string;
  text: string;
  sent_at: string;
  participant_phones: string[];
  attachment: IncomingAttachment | null;
  // The line's ID for this message, so scout can react or reply to it.
  message_id: string;
  // The words of the message this one is a threaded reply to, if it is one.
  reply_to_text: string | null;
};

// What scout asks the bridge to send (src/scout/outgoing.py).
export type ScoutAction =
  // reply_to threads the text under that message.
  | { type: "say"; text: string; reply_to: string | null }
  | { type: "react"; message_id: string; tapback: Tapback; fallback_text: string }
  // A link sent on its own, so iMessage shows it as a card.
  | { type: "link"; url: string }
  // A HermesShare card: a native GUI the group opens from the bubble.
  | {
      type: "card";
      layout: unknown;
      caption: string;
      subcaption?: string | null;
      thumbnail_url: string | null;
      fallback_text: string;
    };

// Read on each call, so tests and the end-to-end runner can point the bridge
// at their own service.
export function scoutUrl(): string {
  return process.env.SCOUT_URL ?? DEFAULT_SCOUT_URL;
}

// A tapback (or other reaction) a member added to a message.
export type IncomingTapback = {
  space_id: string;
  sender_phone: string;
  // A tapback's name ("like"), or the emoji of any other reaction.
  tapback: string;
  // The message it's on, and its words: a poll option's text says which one.
  message_id: string;
  message_text: string | null;
  sent_at: string;
};

export function askScout(text: IncomingText): Promise<ScoutAction[]> {
  return postToScout("/messages", text);
}

export function tellScoutAboutTapback(tapback: IncomingTapback): Promise<ScoutAction[]> {
  return postToScout("/reactions", tapback);
}

async function postToScout(path: string, body: object): Promise<ScoutAction[]> {
  const response = await fetch(`${scoutUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`scout ${path} returned ${response.status}: ${await response.text()}`);
  }
  const { actions } = (await response.json()) as { actions: ScoutAction[] };
  return actions;
}

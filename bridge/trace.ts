// What happened to each message the bridge received, so "why didn't scout
// answer?" can be read straight from the bridge's log. The log reads like the
// chat itself: who said what, then what scout sent back and how long it took.

import type { ScoutAction } from "./scout";
import { tapbackEmoji } from "./tapbacks";

// A message the relay is about to hand to scout, described for people.
export type Arrival = {
  id: string;
  chatId: string;
  senderPhone: string;
  // The words, or what was sent instead, like a tapback or a photo.
  said: string;
  at: Date;
  // When the message reached this bridge, if its line says (Linq does).
  receivedAt: Date | null;
  // When the relay started on it, after any messages ahead of it.
  startedAt: Date;
};

export type MessageOutcome = { id: string; chatId: string | null } & (
  | { kind: "handled"; sent: ScoutAction[]; seconds: number }
  | { kind: "skipped"; reason: string }
  | { kind: "failed"; error: unknown }
);

// How the relay tells its owner about each message: once when it arrives, and
// once when scout has finished with it.
export type RelayReport = {
  arrived(arrival: Arrival): void;
  finished(outcome: MessageOutcome): void;
};

// Returned instead of a message when scout shouldn't see it.
export type Skipped = { skipReason: string };

export function isSkipped(value: object): value is Skipped {
  return typeof (value as Partial<Skipped>).skipReason === "string";
}

// The bridge's own log, in the terminal.
export const consoleReport: RelayReport = {
  arrived: (arrival) => console.log(formatArrival(arrival)),
  finished: (outcome) => {
    const lines = formatOutcome(outcome);
    if (outcome.kind === "failed") console.error(lines, outcome.error);
    else console.log(lines);
  },
};

// Chat IDs are long UUIDs; their first characters are enough to tell groups apart.
const SHORT_CHAT_ID_LENGTH = 8;
// Lines up who's talking and what they said: "…7695" and "scout" fit.
const SPEAKER_WIDTH = 6;
// Everything after the time and chat lines up under the first speaker.
const INDENT = " ".repeat("hh:mm:ss  ".length + SHORT_CHAT_ID_LENGTH + 2);

// Linq normally delivers a message within a second. Much later means its
// webhooks are backed up (see shutdown.ts), which is a bug worth seeing.
const LATE_DELIVERY_SECONDS = 10;
// A long wait behind other messages is expected while scout is busy, but it
// explains a slow reply.
const NOTICEABLE_WAIT_SECONDS = 10;

export function formatArrival(arrival: Arrival): string {
  const { chatId, senderPhone, said, at } = arrival;
  const line = `${clockTime(at)}  ${shortChatId(chatId)}  ${speaker(shortPhone(senderPhone), said)}`;
  return [line, ...describeLateness(arrival)].join("\n");
}

// Only Linq says when a message reached the bridge, so other lines get no notes.
function describeLateness({ at, receivedAt, startedAt }: Arrival): string[] {
  if (!receivedAt) return [];
  const notes: string[] = [];
  const deliverySeconds = (receivedAt.getTime() - at.getTime()) / 1000;
  if (deliverySeconds >= LATE_DELIVERY_SECONDS) {
    notes.push(`${INDENT}⚠ Linq delivered this ${formatDuration(deliverySeconds)} after it was sent`);
  }
  const waitSeconds = (startedAt.getTime() - receivedAt.getTime()) / 1000;
  if (waitSeconds >= NOTICEABLE_WAIT_SECONDS) {
    notes.push(`${INDENT}· waited ${formatDuration(waitSeconds)} for scout to finish the messages before it`);
  }
  return notes;
}

// "45s", or "9m06s" past a minute.
function formatDuration(seconds: number): string {
  const whole = Math.round(seconds);
  if (whole < 60) return `${whole}s`;
  return `${Math.floor(whole / 60)}m${String(whole % 60).padStart(2, "0")}s`;
}

export function formatOutcome(outcome: MessageOutcome): string {
  switch (outcome.kind) {
    case "handled": {
      const took = `${outcome.seconds.toFixed(1)}s`;
      if (outcome.sent.length === 0) return `${INDENT}· no reply (${took})`;
      const replies = outcome.sent.map((action) => INDENT + speaker("scout", describeAction(action)));
      return [...replies, `${INDENT}✓ sent ${countReplies(outcome.sent.length)} in ${took}`].join("\n");
    }
    case "skipped": {
      // Nothing arrived for scout, so this line says when and where itself.
      const time = clockTime(new Date());
      const chat = shortChatId(outcome.chatId ?? "").padEnd(SHORT_CHAT_ID_LENGTH);
      return `${time}  ${chat}  · skipped: ${outcome.reason}`;
    }
    case "failed":
      return `${INDENT}✗ scout couldn't handle it:`;
  }
}

function describeAction(action: ScoutAction): string {
  switch (action.type) {
    case "say":
      return action.reply_to ? `(in a thread) ${action.text}` : action.text;
    case "react":
      return `${tapbackEmoji(action.tapback)} on their message`;
    case "link":
      return `🔗 ${action.url}`;
    case "card":
      return `🃏 card: ${action.caption}`;
  }
}

// A speaker's name, then their words with every line lined up under the first.
function speaker(name: string, words: string): string {
  const continuation = `\n${INDENT}${" ".repeat(SPEAKER_WIDTH + 1)}`;
  return `${name.padEnd(SPEAKER_WIDTH)} ${words.split("\n").join(continuation)}`;
}

function clockTime(at: Date): string {
  return at.toLocaleTimeString("en-GB", { hour12: false });
}

function shortChatId(chatId: string): string {
  return chatId.slice(0, SHORT_CHAT_ID_LENGTH);
}

// scout calls members by their last four digits until they share a name.
function shortPhone(phone: string): string {
  return `…${phone.slice(-4)}`;
}

function countReplies(count: number): string {
  return count === 1 ? "1 reply" : `${count} replies`;
}

export function secondsSince(startedAt: number): number {
  return (performance.now() - startedAt) / 1000;
}

// iMessage's six tapbacks, by the names scout and Linq use. Spectrum carries
// them as emoji: Emoji.like is 👍.

import { Emoji } from "spectrum-ts";

export const TAPBACKS = ["love", "like", "dislike", "laugh", "emphasize", "question"] as const;
export type Tapback = (typeof TAPBACKS)[number];

export function tapbackEmoji(tapback: Tapback): string {
  return Emoji[tapback];
}

export function isTapback(name: string): name is Tapback {
  return (TAPBACKS as readonly string[]).includes(name);
}

// Null for any other emoji, which iMessage shows as a custom reaction.
export function tapbackNamed(emoji: string): Tapback | null {
  return TAPBACKS.find((tapback) => Emoji[tapback] === emoji) ?? null;
}

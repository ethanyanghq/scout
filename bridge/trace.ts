// What happened to each message the bridge received, so "why didn't scout
// answer?" can be read straight from the bridge's log.

export type MessageOutcome = { id: string; chatId: string | null } & (
  | { kind: "handled"; replyCount: number; seconds: number }
  | { kind: "skipped"; reason: string }
  | { kind: "failed"; error: unknown }
);

// Returned instead of a message when scout shouldn't see it.
export type Skipped = { skipReason: string };

export function logOutcome(outcome: MessageOutcome): void {
  const where = outcome.chatId ? ` in ${outcome.chatId}` : "";
  switch (outcome.kind) {
    case "handled":
      console.log(
        `handled ${outcome.id}${where}: ${describeReplies(outcome.replyCount)} in ${outcome.seconds.toFixed(1)}s`,
      );
      return;
    case "skipped":
      console.log(`skipped ${outcome.id}${where}: ${outcome.reason}`);
      return;
    case "failed":
      console.error(`failed ${outcome.id}${where}:`, outcome.error);
      return;
  }
}

export function secondsSince(startedAt: number): number {
  return (performance.now() - startedAt) / 1000;
}

function describeReplies(count: number): string {
  if (count === 0) return "scout stayed quiet";
  return count === 1 ? "1 reply" : `${count} replies`;
}

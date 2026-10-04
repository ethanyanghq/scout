import { describe, expect, test } from "bun:test";
import { formatArrival, formatOutcome } from "./trace";

const CHAT = "ddd37250-088d-4d33-8430-46262d8192ef";
const SENT_AT = new Date(2026, 9, 3, 21, 3, 8);

function secondsAfterSending(seconds: number): Date {
  return new Date(SENT_AT.getTime() + seconds * 1000);
}

function arrival(times: { receivedAt: Date | null; startedAt: Date }) {
  return { id: "message-1", chatId: CHAT, senderPhone: "+16073277695", said: "@scout you there?", at: SENT_AT, ...times };
}

describe("the bridge's log", () => {
  test("shows who said what, in which chat, with a short chat ID and phone", () => {
    const line = formatArrival(arrival({ receivedAt: secondsAfterSending(0.4), startedAt: secondsAfterSending(0.5) }));

    expect(line).toBe("21:03:08  ddd37250  …7695  @scout you there?");
  });

  test("calls out a message Linq delivered long after it was sent", () => {
    const line = formatArrival(arrival({ receivedAt: secondsAfterSending(546), startedAt: secondsAfterSending(546) }));

    expect(line).toEndWith("⚠ Linq delivered this 9m06s after it was sent");
  });

  test("says how long a message waited for scout to finish the ones before it", () => {
    const line = formatArrival(arrival({ receivedAt: secondsAfterSending(1), startedAt: secondsAfterSending(31) }));

    expect(line).toEndWith("· waited 30s for scout to finish the messages before it");
    expect(line).not.toContain("Linq delivered");
  });

  test("adds no timing notes for a line that doesn't say when messages arrived", () => {
    const line = formatArrival(arrival({ receivedAt: null, startedAt: secondsAfterSending(600) }));

    expect(line).toBe("21:03:08  ddd37250  …7695  @scout you there?");
  });

  test("says why a message was skipped", () => {
    const line = formatOutcome({ id: "event-1", chatId: null, kind: "skipped", reason: "a private chat, not a group" });

    expect(line).toEndWith("· skipped: a private chat, not a group");
  });
});

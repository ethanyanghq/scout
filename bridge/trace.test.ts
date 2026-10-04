import { describe, expect, test } from "bun:test";
import { formatArrival, formatOutcome } from "./trace";

const CHAT = "ddd37250-088d-4d33-8430-46262d8192ef";

describe("the bridge's log", () => {
  test("shows who said what, in which chat, with a short chat ID and phone", () => {
    const line = formatArrival({
      id: "message-1",
      chatId: CHAT,
      senderPhone: "+16073277695",
      said: "@scout you there?",
      at: new Date(2026, 9, 3, 21, 3, 8),
    });

    expect(line).toBe("21:03:08  ddd37250  …7695  @scout you there?");
  });

  test("says why a message was skipped", () => {
    const line = formatOutcome({ id: "event-1", chatId: null, kind: "skipped", reason: "a private chat, not a group" });

    expect(line).toEndWith("· skipped: a private chat, not a group");
  });
});

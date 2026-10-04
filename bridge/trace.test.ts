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

  test("lines up scout's replies under the message, then says how long they took", () => {
    const lines = formatOutcome({
      id: "message-1",
      chatId: CHAT,
      kind: "handled",
      sent: [
        { type: "say", text: "Got it, Yuvraj\nStill need your home city", reply_to: null },
        { type: "react", message_id: "message-1", tapback: "like", fallback_text: "Got it" },
      ],
      seconds: 3.72,
    });

    expect(lines.split("\n")).toEqual([
      "                    scout  Got it, Yuvraj",
      "                           Still need your home city",
      "                    scout  👍 on their message",
      "                    ✓ sent 2 replies in 3.7s",
    ]);
  });

  test("shows a card scout sent by its caption", () => {
    const lines = formatOutcome({
      id: "message-1",
      chatId: CHAT,
      kind: "handled",
      sent: [
        { type: "card", layout: {}, caption: "Tulum, Mexico", thumbnail_url: null, fallback_text: "~$1,100" },
      ],
      seconds: 1,
    });

    expect(lines.split("\n")[0]).toBe("                    scout  🃏 card: Tulum, Mexico");
  });

  test("says plainly when scout didn't reply", () => {
    const line = formatOutcome({ id: "message-1", chatId: CHAT, kind: "handled", sent: [], seconds: 0.04 });

    expect(line).toBe("                    · no reply (0.0s)");
  });

  test("says why a message was skipped", () => {
    const line = formatOutcome({ id: "event-1", chatId: null, kind: "skipped", reason: "a private chat, not a group" });

    expect(line).toEndWith("· skipped: a private chat, not a group");
  });
});

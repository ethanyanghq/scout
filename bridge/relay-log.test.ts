import { describe, expect, test } from "bun:test";
import { isWorthShowing } from "./relay-log";

describe("the Linq relay's lines in bun run dev", () => {
  test("hides events it forwarded successfully, since the bridge logs each message", () => {
    const line = "9:00:04 PM  message.received   → http://127.0.0.1:8788/linq-events  [204 No Content]  (11ms)";

    expect(isWorthShowing(line)).toBe(false);
  });

  test("shows events the bridge failed to take", () => {
    const line = "9:00:04 PM  message.received   → http://127.0.0.1:8788/linq-events  [500 Internal Server Error]  (11ms)";

    expect(isWorthShowing(line)).toBe(true);
  });

  test("never shows the webhook's signing secret", () => {
    expect(isWorthShowing("Signing secret: whsec_abc123 (this session only)")).toBe(false);
  });

  test("shows whether the relay is connected", () => {
    expect(isWorthShowing("Connected to relay")).toBe(true);
  });
});

import { describe, expect, test } from "bun:test";
import { isWorthShowing } from "./relay-log";

describe("the Linq relay's lines in bun run dev", () => {
  test("never shows the webhook's signing secret", () => {
    expect(isWorthShowing("Signing secret: whsec_abc123 (this session only)")).toBe(false);
  });
});

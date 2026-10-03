import { describe, expect, test } from "bun:test";
import { toJpeg } from "./scout";

describe("converting a photo for scout", () => {
  // Only machines without sips (anything but a Mac) can show this.
  test.if(!Bun.which("sips"))("explains that photos need a Mac", async () => {
    await expect(toJpeg(Buffer.from("receipt"))).rejects.toThrow(
      "Photos need macOS's sips to become JPEGs, so they only work on a Mac.",
    );
  });
});

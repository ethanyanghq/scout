import { afterAll, describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { readEnvFile } from "./env-file";

const folder = await mkdtemp(join(tmpdir(), "scout-env-file-"));
afterAll(() => rm(folder, { recursive: true, force: true }));

describe("reading an env file", () => {
  test("reads settings, skipping comments and commented-out lines", async () => {
    const path = join(folder, "settings.env");
    await Bun.write(
      path,
      `# Required.
ANTHROPIC_API_KEY=sk-ant-123
# SCOUT_DB_PATH=old.db
IMESSAGE_MODE = "linq"
GOOGLE_PLACES_API_KEY=
`,
    );

    expect(await readEnvFile(path)).toEqual({
      ANTHROPIC_API_KEY: "sk-ant-123",
      IMESSAGE_MODE: "linq",
      GOOGLE_PLACES_API_KEY: "",
    });
  });

  test("returns nothing for a file that doesn't exist", async () => {
    expect(await readEnvFile(join(folder, "missing.env"))).toBeNull();
  });
});

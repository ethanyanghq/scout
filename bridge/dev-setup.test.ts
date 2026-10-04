import { describe, expect, test } from "bun:test";
import { findSetupProblems, type DevSetup } from "./dev-setup";

// A Mac set up for a Linq line, with nothing wrong.
function linqSetup(changes: Partial<DevSetup> = {}): DevSetup {
  return {
    isMac: true,
    serviceSettings: { ANTHROPIC_API_KEY: "sk-ant-123" },
    bridgeSettings: { IMESSAGE_MODE: "linq", LINQ_API_KEY: "linq-123" },
    installed: { uv: true, linq: true },
    linqLoggedIn: true,
    busyPorts: [],
    ...changes,
  };
}

describe("checking the setup before bun run dev starts anything", () => {
  test("finds nothing wrong with a ready Linq setup", () => {
    expect(findSetupProblems(linqSetup())).toEqual([]);
  });

  test("asks for an AI key when there isn't one", () => {
    const setup = linqSetup({ serviceSettings: { ANTHROPIC_API_KEY: "" } });

    expect(findSetupProblems(setup)).toEqual(["Set ANTHROPIC_API_KEY (or OPENAI_API_KEY) in .env."]);
  });

  test("accepts an OpenAI key in place of the Anthropic key", () => {
    const setup = linqSetup({ serviceSettings: { OPENAI_API_KEY: "sk-123" } });

    expect(findSetupProblems(setup)).toEqual([]);
  });
});

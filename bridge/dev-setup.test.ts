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

  test("asks for the service's settings file when there isn't one", () => {
    expect(findSetupProblems(linqSetup({ serviceSettings: null }))).toEqual([
      "Create the service's settings: cp .env.example .env, then fill in ANTHROPIC_API_KEY.",
    ]);
  });

  test("asks for an AI key when there isn't one", () => {
    const setup = linqSetup({ serviceSettings: { ANTHROPIC_API_KEY: "" } });

    expect(findSetupProblems(setup)).toEqual(["Set ANTHROPIC_API_KEY (or OPENAI_API_KEY) in .env."]);
  });

  test("accepts an OpenAI key in place of the Anthropic key", () => {
    const setup = linqSetup({ serviceSettings: { OPENAI_API_KEY: "sk-123" } });

    expect(findSetupProblems(setup)).toEqual([]);
  });

  test("asks for uv when it isn't installed", () => {
    const setup = linqSetup({ installed: { uv: false, linq: true } });

    expect(findSetupProblems(setup)).toEqual([
      "Install uv, which runs the scout service: https://docs.astral.sh/uv/",
    ]);
  });

  test("in Linq mode, asks for the key, the CLI and a login", () => {
    const noKey = linqSetup({ bridgeSettings: { IMESSAGE_MODE: "linq" } });
    const noCli = linqSetup({ installed: { uv: true, linq: false }, linqLoggedIn: null });
    const loggedOut = linqSetup({ linqLoggedIn: false });

    expect(findSetupProblems(noKey)).toEqual([
      "Set LINQ_API_KEY in bridge/.env (from `linq signup` or the Linq dashboard).",
    ]);
    expect(findSetupProblems(noCli)).toEqual([
      "Install the Linq CLI, which relays Linq's events here: npm i -g @linqapp/cli",
    ]);
    expect(findSetupProblems(loggedOut)).toEqual([
      "Log the Linq CLI in: linq login (or linq signup for a new line).",
    ]);
  });

  test("in cloud mode, asks for each missing Photon setting", () => {
    const setup = linqSetup({ bridgeSettings: { IMESSAGE_MODE: "cloud", PHOTON_PROJECT_ID: "p-1" } });

    expect(findSetupProblems(setup)).toEqual([
      "Set PHOTON_PROJECT_SECRET in bridge/.env (from your Photon project).",
    ]);
  });

  test("local mode, the default, needs a Mac", () => {
    const setup = linqSetup({ isMac: false, bridgeSettings: {} });

    expect(findSetupProblems(setup)).toEqual([
      "Local mode needs a Mac signed into Messages. For a Linq line, set IMESSAGE_MODE=linq in bridge/.env.",
    ]);
  });

  test("names the modes when IMESSAGE_MODE is something else", () => {
    const setup = linqSetup({ bridgeSettings: { IMESSAGE_MODE: "sms" } });

    expect(findSetupProblems(setup)).toEqual([
      'IMESSAGE_MODE in bridge/.env must be local, cloud or linq, not "sms".',
    ]);
  });

  test("says which port is taken", () => {
    const setup = linqSetup({ busyPorts: [{ port: 8787, usedBy: "the scout service" }] });

    expect(findSetupProblems(setup)).toEqual([
      "Port 8787 (the scout service) is already in use. Is scout already running?",
    ]);
  });
});

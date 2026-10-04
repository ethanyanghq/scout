import { describe, expect, test } from "bun:test";
import { findSetupProblems, isTunnelStatus, publicDomain, type DevSetup } from "./dev-setup";

// A Mac set up for a Linq line, with nothing wrong.
function linqSetup(changes: Partial<DevSetup> = {}): DevSetup {
  return {
    isMac: true,
    serviceSettings: { ANTHROPIC_API_KEY: "sk-ant-123" },
    bridgeSettings: { IMESSAGE_MODE: "linq", LINQ_API_KEY: "linq-123" },
    installed: { uv: true, linq: true, ngrok: true },
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

  test("needs ngrok installed when the calendar links are public", () => {
    const setup = linqSetup({
      serviceSettings: { ANTHROPIC_API_KEY: "sk-ant-123", SCOUT_PUBLIC_URL: "https://scout.ngrok-free.dev" },
      installed: { uv: true, linq: true, ngrok: false },
    });

    expect(findSetupProblems(setup)).toEqual([expect.stringContaining("Install ngrok")]);
  });

  test("rejects a public address that isn't a URL", () => {
    const setup = linqSetup({
      serviceSettings: { ANTHROPIC_API_KEY: "sk-ant-123", SCOUT_PUBLIC_URL: "scout.ngrok-free.dev" },
    });

    expect(findSetupProblems(setup)).toEqual([expect.stringContaining("must be a full address")]);
  });
});

describe("the public calendar tunnel", () => {
  test("serves the domain from the public address", () => {
    expect(publicDomain({ SCOUT_PUBLIC_URL: "https://scout.ngrok-free.dev/" })).toBe("scout.ngrok-free.dev");
    expect(publicDomain({})).toBeNull();
  });

  test("shows when the tunnel starts and when it has trouble, but not every request", () => {
    expect(isTunnelStatus('t=2026 lvl=info msg="started tunnel" url=https://scout.ngrok-free.dev')).toBe(true);
    expect(isTunnelStatus('t=2026 lvl=eror msg="failed to auth"')).toBe(true);
    expect(isTunnelStatus('t=2026 lvl=info msg="join connections" obj=join')).toBe(false);
  });
});

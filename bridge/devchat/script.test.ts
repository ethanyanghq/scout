import { describe, expect, test } from "bun:test";
import { checkExpectation, parseScript, type Expectation } from "./script";

const FOLDER = "/repo/bridge/e2e";

function scout(...texts: string[]) {
  return texts.map((text, index) => ({ id: `m${index + 2}`, from: "scout", text }));
}

describe("reading a console script", () => {
  test("reads the members, starting stage, messages, photos and checks in order", () => {
    const script = parseScript(
      `# Plain votes close the poll.
      members Maya leo
      from poll-open

      maya: 2
      leo photo receipts/airbnb.jpg
      expect scout ~ "San Juan"
      expect scout quiet
      expect state destination = "San Juan, Puerto Rico"
      expect state members.0.home_city ~ "boston"`,
      FOLDER,
    );

    expect(script.members).toEqual(["maya", "leo"]);
    expect(script.from).toBe("poll-open");
    expect(script.steps.map(({ line, source, ...step }) => step)).toEqual([
      { kind: "say", member: "maya", text: "2" },
      { kind: "photo", member: "leo", path: "/repo/bridge/e2e/receipts/airbnb.jpg" },
      { kind: "expect-reply", contains: "San Juan" },
      { kind: "expect-quiet" },
      { kind: "expect-state", path: "destination", matcher: "=", expected: "San Juan, Puerto Rico" },
      { kind: "expect-state", path: "members.0.home_city", matcher: "~", expected: "boston" },
    ]);
  });

  test("reads tapbacks on scout's latest message or on one with given words", () => {
    const script = parseScript(
      'members maya leo\nmaya react like "San Juan"\nleo react love scout.last',
      FOLDER,
    );

    expect(script.steps.map(({ line, source, ...step }) => step)).toEqual([
      { kind: "react", member: "maya", tapback: "like", target: "San Juan" },
      { kind: "react", member: "leo", tapback: "love", target: "scout.last" },
    ]);
  });

  test("reads threaded replies and checks on them", () => {
    const script = parseScript(
      'members maya\nmaya reply "2. San Juan": this one: for real\nmaya reply scout.last: ok\nexpect thread ~ "Got it"',
      FOLDER,
    );

    expect(script.steps.map(({ line, source, ...step }) => step)).toEqual([
      { kind: "reply", member: "maya", target: "2. San Juan", text: "this one: for real" },
      { kind: "reply", member: "maya", target: "scout.last", text: "ok" },
      { kind: "expect-thread", contains: "Got it" },
    ]);
  });
});

describe("checking what scout did", () => {
  test("a reply check passes when any reply contains the words, ignoring case", () => {
    const expectation: Expectation = { kind: "expect-reply", contains: "san juan wins" };

    const result = checkExpectation(expectation, {
      replies: scout("🎉 Poll closed! San Juan Wins with 2 of 3 votes.", "📅 Locked in"),
      trip: null,
    });

    expect(result.passed).toBe(true);
  });

  test("a quiet check passes only when scout didn't reply", () => {
    const expectation: Expectation = { kind: "expect-quiet" };

    expect(checkExpectation(expectation, { replies: [], trip: null }).passed).toBe(true);
    expect(checkExpectation(expectation, { replies: scout("lol"), trip: null }).passed).toBe(false);
  });

  test("an exact state check follows a dotted path into the trip", () => {
    const trip = { stage: "voting", members: [{ budget_usd: 800 }, { budget_usd: 600 }] };
    const check = (path: string, expected: unknown) =>
      checkExpectation({ kind: "expect-state", path, matcher: "=", expected }, { replies: [], trip });

    expect(check("members.1.budget_usd", 600).passed).toBe(true);
    expect(check("stage", "voting").passed).toBe(true);
    expect(check("stage", "destination_chosen")).toEqual({
      passed: false,
      detail: 'stage is "voting"',
    });
  });
});

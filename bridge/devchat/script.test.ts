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

  test("reads checks on a link card", () => {
    const script = parseScript(
      'members maya\nexpect card title ~ "San Juan"\nexpect card url ~ "calendar.google.com"\nexpect card no warnings',
      FOLDER,
    );

    expect(script.steps.map(({ line, source, ...step }) => step)).toEqual([
      { kind: "expect-card", field: "title", contains: "San Juan" },
      { kind: "expect-card", field: "url", contains: "calendar.google.com" },
      { kind: "expect-card-clean" },
    ]);
  });

  test("keeps colons inside a message", () => {
    const script = parseScript("members maya\nmaya: @scout plan it: not too packed", FOLDER);

    expect(script.steps[0]).toMatchObject({ kind: "say", text: "@scout plan it: not too packed" });
  });

  test("remembers each step's line, for pointing at failures", () => {
    const script = parseScript("members maya\n\nmaya: hi", FOLDER);

    expect(script.steps[0]).toMatchObject({ line: 3, source: "maya: hi" });
  });

  test("points at a message from someone who isn't a member", () => {
    expect(() => parseScript("members maya leo\njordan: hi", FOLDER)).toThrow(
      "line 2: jordan isn't in members (maya, leo)",
    );
  });

  test("needs the members before the first message", () => {
    expect(() => parseScript("maya: hi\nmembers maya", FOLDER)).toThrow(
      'line 1: put the "members" line before any message',
    );
  });

  test("needs a members line", () => {
    expect(() => parseScript("expect scout quiet", FOLDER)).toThrow('a script needs a "members" line');
  });

  test("points at a line it doesn't understand", () => {
    expect(() => parseScript("members maya\nmaya says hi", FOLDER)).toThrow(
      'line 2: I don\'t understand "maya says hi"',
    );
  });

  test("reads a tapback check, and names the tapbacks when one is wrong", () => {
    const script = parseScript("members maya\nexpect scout reacted like", FOLDER);

    expect(script.steps[0]).toMatchObject({ kind: "expect-tapback", tapback: "like" });
    expect(() => parseScript("members maya\nexpect scout reacted thumbs", FOLDER)).toThrow(
      'line 2: a tapback is one of love, like, dislike, laugh, emphasize, question, not "thumbs"',
    );
  });

  test("names the stages a script can start from", () => {
    expect(() => parseScript("members maya\nfrom the-end", FOLDER)).toThrow(
      'line 2: "from" must be one of poll-open, destination-chosen, not "the-end"',
    );
  });

  test("asks for quotes around text in a check", () => {
    expect(() => parseScript("members maya\nexpect state destination = San Juan", FOLDER)).toThrow(
      "line 2: San Juan isn't a value scripts understand",
    );
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

  test("a failed reply check says what scout said instead", () => {
    const expectation: Expectation = { kind: "expect-reply", contains: "Tulum" };

    const result = checkExpectation(expectation, { replies: scout("Got it", "2 of 3 voted"), trip: null });

    expect(result).toEqual({ passed: false, detail: "scout said: Got it / 2 of 3 voted" });
  });

  test("a without check fails when any reply has the words, and passes when scout stays quiet", () => {
    const expectation: Expectation = { kind: "expect-reply-without", words: "2.236" };

    expect(checkExpectation(expectation, { replies: scout("√5 is about 2.236"), trip: null }).passed).toBe(false);
    expect(checkExpectation(expectation, { replies: scout("dunno, anyway"), trip: null }).passed).toBe(true);
    expect(checkExpectation(expectation, { replies: [], trip: null }).passed).toBe(true);
  });

  test("a quiet check passes only when scout didn't reply", () => {
    const expectation: Expectation = { kind: "expect-quiet" };

    expect(checkExpectation(expectation, { replies: [], trip: null }).passed).toBe(true);
    expect(checkExpectation(expectation, { replies: scout("lol"), trip: null }).passed).toBe(false);
  });

  test("a tapback check passes when scout added that tapback", () => {
    const thumbsUp = { id: "m2", from: "scout", text: "👍 on m1", tapback: "like", on: "m1" };

    const liked = checkExpectation({ kind: "expect-tapback", tapback: "like" }, { replies: [thumbsUp], trip: null });
    const loved = checkExpectation({ kind: "expect-tapback", tapback: "love" }, { replies: [thumbsUp], trip: null });

    expect(liked.passed).toBe(true);
    expect(loved).toEqual({ passed: false, detail: "scout said: 👍 on m1" });
  });

  test("a thread check only counts replies scout threaded under a message", () => {
    const loose = { id: "m2", from: "scout", text: "Got it, Maya" };
    const threaded = { ...loose, replyTo: "m1" };
    const expectation: Expectation = { kind: "expect-thread", contains: "got it" };

    expect(checkExpectation(expectation, { replies: [threaded], trip: null }).passed).toBe(true);
    expect(checkExpectation(expectation, { replies: [loose], trip: null }).passed).toBe(false);
  });

  test("card checks look at the link card scout sent", () => {
    const card = {
      url: "https://example.com/trip",
      title: "San Juan wins",
      description: null,
      imageUrl: null,
      imageFile: null,
      warnings: ["No image: the card would have no picture."],
    };
    const replies = [{ id: "m2", from: "scout", text: card.url, card }];

    const title = checkExpectation({ kind: "expect-card", field: "title", contains: "san juan" }, { replies, trip: null });
    const clean = checkExpectation({ kind: "expect-card-clean" }, { replies, trip: null });
    const noCard = checkExpectation({ kind: "expect-card-clean" }, { replies: [], trip: null });

    expect(title.passed).toBe(true);
    expect(clean).toEqual({ passed: false, detail: "warnings: No image: the card would have no picture." });
    expect(noCard).toEqual({ passed: false, detail: "scout sent no link card. scout didn't reply" });
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

  test("a state check reports a missing value as null", () => {
    const result = checkExpectation(
      { kind: "expect-state", path: "open_poll.votes", matcher: "=", expected: {} },
      { replies: [], trip: { open_poll: null } },
    );

    expect(result).toEqual({ passed: false, detail: "open_poll.votes is null" });
  });

  test("a contains check finds text inside a value, ignoring case", () => {
    const result = checkExpectation(
      { kind: "expect-state", path: "members.0.home_city", matcher: "~", expected: "boston" },
      { replies: [], trip: { members: [{ home_city: "Boston, MA" }] } },
    );

    expect(result.passed).toBe(true);
  });
});

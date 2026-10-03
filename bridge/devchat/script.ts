// Console scripts: plain-text files that play a group conversation and check
// what scout did. They read like the chat:
//
//   # Plain votes close the poll.
//   members maya leo priya
//   from poll-open
//
//   maya: 2
//   leo: 2
//   priya: 1
//   expect scout ~ "San Juan"
//   expect state destination = "San Juan, Puerto Rico"
//
// Claude words things differently on every run, so scripts check the trip's
// state, or a word a reply must contain, never whole replies.

import { resolve } from "node:path";
import { readPhoto, type ChatEntry, type DevChat, type Exchange } from "./platform";
import { SEED_STAGES, showTrip, type SeedStage } from "./trips";

export type Script = { members: string[]; from: SeedStage | null; steps: Step[] };

type StepSource = { line: number; source: string };
export type Step = StepSource &
  (
    | { kind: "say"; member: string; text: string }
    | { kind: "photo"; member: string; path: string }
    | Expectation
  );
export type Expectation =
  | { kind: "expect-reply"; contains: string }
  | { kind: "expect-quiet" }
  | { kind: "expect-state"; path: string; matcher: "=" | "~"; expected: unknown };

// What the checks look at: scout's replies to the latest message, and the trip.
export type CheckContext = { replies: ChatEntry[]; trip: unknown };
export type CheckResult = { passed: boolean; detail: string };

export type ScriptEvent =
  | { kind: "exchange"; exchange: Exchange }
  | { kind: "check"; step: Step; result: CheckResult };

const STEP_PATTERNS = {
  members: /^members\s+(.+)$/,
  from: /^from\s+(\S+)$/,
  say: /^(\w+):\s*(.+)$/,
  photo: /^(\w+)\s+photo\s+(.+)$/,
  expectQuiet: /^expect\s+scout\s+quiet$/,
  expectReply: /^expect\s+scout\s+~\s+(".*")$/,
  expectState: /^expect\s+state\s+(\S+)\s+(=|~)\s+(.+)$/,
};

// Photo paths are relative to the script's folder.
export function parseScript(text: string, scriptFolder: string): Script {
  const script: Script = { members: [], from: null, steps: [] };
  text.split("\n").forEach((rawLine, index) => {
    const source = rawLine.trim();
    if (source === "" || source.startsWith("#")) return;
    try {
      readLine(script, { line: index + 1, source }, scriptFolder);
    } catch (error) {
      throw new Error(`line ${index + 1}: ${(error as Error).message}`);
    }
  });
  if (script.members.length === 0) throw new Error('a script needs a "members" line');
  return script;
}

// Plays the script in the chat, stopping at the first message scout couldn't
// handle or the first failed check. Returns whether everything passed.
export async function runScript(
  script: Script,
  chat: DevChat,
  report: (event: ScriptEvent) => void,
): Promise<boolean> {
  let latestReplies: ChatEntry[] = [];
  for (const step of script.steps) {
    if (step.kind === "say" || step.kind === "photo") {
      const exchange =
        step.kind === "say"
          ? await chat.say(step.member, step.text)
          : await chat.sendPhoto(step.member, await readPhoto(step.path));
      report({ kind: "exchange", exchange });
      if (exchange.outcome.kind === "failed") return false;
      latestReplies = exchange.replies;
      continue;
    }

    const trip = step.kind === "expect-state" ? await showTrip(chat.chatId) : null;
    const result = checkExpectation(step, { replies: latestReplies, trip });
    report({ kind: "check", step, result });
    if (!result.passed) return false;
  }
  return true;
}

export function checkExpectation(expectation: Expectation, context: CheckContext): CheckResult {
  const said = context.replies.map((reply) => reply.text);
  const whatScoutSaid = said.length ? `scout said: ${said.join(" / ")}` : "scout didn't reply";

  switch (expectation.kind) {
    case "expect-quiet":
      return { passed: said.length === 0, detail: whatScoutSaid };
    case "expect-reply": {
      const wanted = expectation.contains.toLowerCase();
      return { passed: said.some((text) => text.toLowerCase().includes(wanted)), detail: whatScoutSaid };
    }
    case "expect-state": {
      const actual = valueAt(context.trip, expectation.path);
      const passed =
        expectation.matcher === "="
          ? Bun.deepEquals(actual, expectation.expected)
          : JSON.stringify(actual ?? null)
              .toLowerCase()
              .includes(String(expectation.expected).toLowerCase());
      return { passed, detail: `${expectation.path} is ${JSON.stringify(actual ?? null)}` };
    }
  }
}

function readLine(script: Script, at: StepSource, scriptFolder: string): void {
  const { source } = at;
  let match: RegExpMatchArray | null;

  if ((match = source.match(STEP_PATTERNS.members))) {
    script.members = match[1]!.toLowerCase().split(/\s+/);
  } else if ((match = source.match(STEP_PATTERNS.from))) {
    script.from = readStage(match[1]!);
  } else if ((match = source.match(STEP_PATTERNS.expectQuiet))) {
    script.steps.push({ ...at, kind: "expect-quiet" });
  } else if ((match = source.match(STEP_PATTERNS.expectReply))) {
    script.steps.push({ ...at, kind: "expect-reply", contains: readQuoted(match[1]!) });
  } else if ((match = source.match(STEP_PATTERNS.expectState))) {
    const [, path, matcher, value] = match as [string, string, "=" | "~", string];
    const expected = matcher === "=" ? readJson(value) : readQuoted(value);
    script.steps.push({ ...at, kind: "expect-state", path, matcher, expected });
  } else if ((match = source.match(STEP_PATTERNS.photo))) {
    const member = readMember(script, match[1]!);
    script.steps.push({ ...at, kind: "photo", member, path: resolve(scriptFolder, match[2]!) });
  } else if ((match = source.match(STEP_PATTERNS.say))) {
    script.steps.push({ ...at, kind: "say", member: readMember(script, match[1]!), text: match[2]! });
  } else {
    throw new Error(`I don't understand "${source}"`);
  }
}

function readMember(script: Script, name: string): string {
  if (script.members.length === 0) throw new Error('put the "members" line before any message');
  const member = name.toLowerCase();
  if (!script.members.includes(member)) {
    throw new Error(`${name} isn't in members (${script.members.join(", ")})`);
  }
  return member;
}

function readStage(value: string): SeedStage {
  const stage = SEED_STAGES.find((candidate) => candidate === value);
  if (!stage) throw new Error(`"from" must be one of ${SEED_STAGES.join(", ")}, not "${value}"`);
  return stage;
}

function readQuoted(value: string): string {
  const text = readJson(value);
  if (typeof text !== "string") throw new Error(`put the text in double quotes: ${value}`);
  return text;
}

function readJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${value} isn't a value scripts understand; use "text", a number, true, false or null`);
  }
}

// Follows a dotted path such as "members.0.budget_usd" into the trip.
function valueAt(trip: unknown, path: string): unknown {
  return path
    .split(".")
    .reduce<unknown>((value, key) => (value as Record<string, unknown> | null)?.[key], trip);
}

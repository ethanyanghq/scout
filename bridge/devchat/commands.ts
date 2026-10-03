// The developer console: play a whole group chat with scout from the
// terminal, through the real bridge and the running scout service. Each
// command runs on its own, so an AI agent can drive it one shell command at a
// time. See DEVELOPING.md.

import { basename, dirname } from "node:path";
import { parseArgs } from "node:util";
import { scoutUrl } from "../scout";
import { DevChat, connectDevChat, readPhoto, type ChatEntry, type Exchange } from "./platform";
import { parseScript, runScript, type ScriptEvent } from "./script";
import { loadSession, saveSession, type Session } from "./session";
import { TAPBACKS, isTapback } from "../tapbacks";
import { SEED_STAGES, resetTrip, seedTrip, showMessages, showTrip, type SeedStage } from "./trips";

const USAGE = `Usage (from bridge/, with the scout service running):
  bun run devchat start maya leo priya [--from ${SEED_STAGES.join("|")}]
  bun run devchat say maya "hey @scout, spring break?"
  bun run devchat react priya like "2. San Juan"  (or a message ID, or scout.last)
  bun run devchat reply maya "2. San Juan" this one!
  bun run devchat photo leo receipts/airbnb.jpg
  bun run devchat transcript
  bun run devchat state [--chat <chat id>]
  bun run devchat reset [--chat <chat id>]
  bun run devchat run e2e/vote.chat`;

try {
  await runCommand(process.argv.slice(2));
} catch (error) {
  console.error(describeError(error));
  process.exitCode = 1;
}

async function runCommand([command, ...args]: string[]): Promise<void> {
  switch (command) {
    case "start":
      return start(args);
    case "say":
      return say(args);
    case "react":
      return react(args);
    case "reply":
      return replyInThread(args);
    case "photo":
      return sendPhoto(args);
    case "transcript":
      return printTranscript();
    case "state":
      return printTrip(args);
    case "reset":
      return reset(args);
    case "run":
      return run(args);
    default:
      throw new Error(USAGE);
  }
}

async function start(args: string[]): Promise<void> {
  const { positionals: names, values } = parseArgs({
    args,
    options: { from: { type: "string" } },
    allowPositionals: true,
  });
  if (names.length === 0) throw new Error(`Name at least one member.\n\n${USAGE}`);
  const stage = values.from === undefined ? null : readStage(values.from);
  await startChat(names, stage);
}

async function say([name, ...words]: string[]): Promise<void> {
  if (!name || words.length === 0) throw new Error(USAGE);
  await sendInSavedChat((chat) => chat.say(name, words.join(" ")));
}

async function react([name, tapback, target]: string[]): Promise<void> {
  if (!name || !tapback || !target) throw new Error(USAGE);
  if (!isTapback(tapback)) {
    throw new Error(`A tapback is one of ${TAPBACKS.join(", ")}, not "${tapback}".`);
  }
  await sendInSavedChat((chat) => chat.react(name, target, tapback));
}

async function replyInThread([name, target, ...words]: string[]): Promise<void> {
  if (!name || !target || words.length === 0) throw new Error(USAGE);
  await sendInSavedChat((chat) => chat.reply(name, target, words.join(" ")));
}

async function sendPhoto([name, path]: string[]): Promise<void> {
  if (!name || !path) throw new Error(USAGE);
  const photo = await readPhoto(path);
  await sendInSavedChat((chat) => chat.sendPhoto(name, photo));
}

async function printTranscript(): Promise<void> {
  const { chatId, transcript } = await loadSession();
  console.log(`${chatId}:`);
  if (transcript.length === 0) console.log("(no messages yet)");
  transcript.forEach(printEntry);
}

async function printTrip(args: string[]): Promise<void> {
  const chatId = await chosenChatId(args);
  console.log(JSON.stringify(await showTrip(chatId), null, 2));
}

async function reset(args: string[]): Promise<void> {
  const { values } = parseArgs({ args, options: { chat: { type: "string" } } });
  // --chat names another chat, such as a real group's, and leaves the
  // console's own chat alone.
  if (values.chat !== undefined) {
    await resetTrip(values.chat);
    console.log(`Reset ${values.chat}'s trip. Its next message starts over.`);
    return;
  }
  const session = await loadSession();
  await resetTrip(session.chatId);
  await saveSession({ ...session, transcript: [] });
  console.log(`Reset ${session.chatId}: its trip and transcript are cleared.`);
}

// Plays a script in a new chat and saves the chat afterwards, so transcript
// and state can show what happened.
async function run([path]: string[]): Promise<void> {
  if (!path) throw new Error(USAGE);
  const file = Bun.file(path);
  if (!(await file.exists())) throw new Error(`There's no script at ${path}.`);
  const script = parseScript(await file.text(), dirname(path));

  const session = await startChat(script.members, script.from);
  const chat = new DevChat(session.chatId, session.members, session.transcript);
  const stop = await connectDevChat(chat);
  let passed: boolean;
  try {
    passed = await runScript(script, chat, printScriptEvent);
  } finally {
    await stop();
    await saveSession({ ...session, transcript: chat.transcript });
  }
  console.log(passed ? `✓ ${basename(path)} passed` : `✗ ${basename(path)} failed`);
  if (!passed) process.exitCode = 1;
}

// Starts a new chat, seeded at a stage if one is given, and saves it as the
// console's current chat.
async function startChat(names: string[], stage: SeedStage | null): Promise<Session> {
  // The same numbers scout-simulate uses, so transcripts read alike.
  const members = names.map((name, index) => ({
    name: name.toLowerCase(),
    phone: `+1555000${String(index + 1).padStart(4, "0")}`,
  }));
  const chatId = `devchat-${crypto.randomUUID().slice(0, 8)}`;
  if (stage) {
    const named = members.map((member) => ({ phone: member.phone, name: capitalize(member.name) }));
    await seedTrip(chatId, stage, named);
  }
  // A seeded chat starts with what scout "said" to get there, such as the poll,
  // so members can vote on it with a tapback.
  const seeded = stage ? await showMessages(chatId) : [];
  const transcript = seeded
    .filter((message) => message.sender_phone === null)
    .map((message, index) => ({ id: `m${index + 1}`, from: "scout", text: message.text }));
  const session = { chatId, members, transcript };
  await saveSession(session);

  const roster = members.map((member) => `${member.name} (${member.phone})`).join(", ");
  console.log(`Started ${chatId} with ${roster}.`);
  if (stage) console.log(`It starts at ${stage}, where scout has already said:`);
  transcript.forEach(printEntry);
  return session;
}

// Reopens the saved chat, sends one message through the bridge, prints what
// happened, and saves the chat again.
async function sendInSavedChat(send: (chat: DevChat) => Promise<Exchange>): Promise<void> {
  const session = await loadSession();
  const chat = new DevChat(session.chatId, session.members, session.transcript);
  const stop = await connectDevChat(chat);
  let exchange: Exchange;
  try {
    exchange = await send(chat);
  } finally {
    await stop();
    await saveSession({ ...session, transcript: chat.transcript });
  }
  printExchange(exchange);
}

function printExchange({ sent, outcome, replies }: Exchange): void {
  printEntry(sent);
  replies.forEach(printEntry);
  if (outcome.kind === "skipped") {
    console.log(`(the bridge skipped it: ${outcome.reason})`);
  } else if (outcome.kind === "failed") {
    console.error(`(scout couldn't handle it: ${describeError(outcome.error)})`);
    process.exitCode = 1;
  } else if (replies.length === 0) {
    console.log("(scout stayed quiet)");
  }
}

function printScriptEvent(event: ScriptEvent): void {
  if (event.kind === "exchange") {
    printExchange(event.exchange);
    return;
  }
  const { step, result } = event;
  if (result.passed) {
    console.log(`  ✓ ${step.source}`);
  } else {
    console.log(`  ✗ ${step.source} (line ${step.line})\n    ${result.detail}`);
  }
}

function printEntry(entry: ChatEntry): void {
  const thread = entry.replyTo ? ` ↪ ${entry.replyTo}` : "";
  console.log(`[${entry.id}] ${entry.from}${thread}: ${entry.text}`);
}

function readStage(value: string): SeedStage {
  const stage = SEED_STAGES.find((candidate) => candidate === value);
  if (!stage) throw new Error(`--from must be one of ${SEED_STAGES.join(", ")}, not "${value}".`);
  return stage;
}

async function chosenChatId(args: string[]): Promise<string> {
  const { values } = parseArgs({ args, options: { chat: { type: "string" } } });
  return values.chat ?? (await loadSession()).chatId;
}

function capitalize(name: string): string {
  return name.charAt(0).toUpperCase() + name.slice(1);
}

function describeError(error: unknown): string {
  if (error instanceof Error && "code" in error && error.code === "ConnectionRefused") {
    return `Couldn't reach scout at ${scoutUrl()}. Start it first: uv run --env-file .env scout-server`;
  }
  return error instanceof Error ? error.message : String(error);
}

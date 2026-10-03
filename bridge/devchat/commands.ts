// The developer console: play a whole group chat with scout from the
// terminal, through the real bridge and the running scout service. Each
// command runs on its own, so an AI agent can drive it one shell command at a
// time. See DEVELOPING.md.

import { basename } from "node:path";
import { parseArgs } from "node:util";
import { scoutUrl } from "../scout";
import { DevChat, connectDevChat, type ChatEntry, type Exchange } from "./platform";
import { loadSession, saveSession } from "./session";
import { SEED_STAGES, resetTrip, seedTrip, showTrip, type SeedStage, type TripSummary } from "./trips";

const USAGE = `Usage (from bridge/, with the scout service running):
  bun run devchat start maya leo priya [--from ${SEED_STAGES.join("|")}]
  bun run devchat say maya "hey @scout, spring break?"
  bun run devchat photo leo receipts/airbnb.jpg
  bun run devchat transcript
  bun run devchat state [--chat <chat id>]
  bun run devchat reset [--chat <chat id>]`;

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
    case "photo":
      return sendPhoto(args);
    case "transcript":
      return printTranscript();
    case "state":
      return printTrip(args);
    case "reset":
      return reset(args);
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

  // The same numbers scout-simulate uses, so transcripts read alike.
  const members = names.map((name, index) => ({
    name: name.toLowerCase(),
    phone: `+1555000${String(index + 1).padStart(4, "0")}`,
  }));
  const chatId = `devchat-${crypto.randomUUID().slice(0, 8)}`;
  const stage = values.from === undefined ? null : readStage(values.from);
  const trip = stage
    ? await seedTrip(
        chatId,
        stage,
        members.map((member) => ({ phone: member.phone, name: capitalize(member.name) })),
      )
    : null;
  await saveSession({ chatId, members, transcript: [] });

  const roster = members.map((member) => `${member.name} (${member.phone})`).join(", ");
  console.log(`Started ${chatId} with ${roster}.`);
  if (trip) console.log(describeSeededTrip(trip));
}

async function say([name, ...words]: string[]): Promise<void> {
  if (!name || words.length === 0) throw new Error(USAGE);
  await sendInSavedChat((chat) => chat.say(name, words.join(" ")));
}

async function sendPhoto([name, path]: string[]): Promise<void> {
  if (!name || !path) throw new Error(USAGE);
  const file = Bun.file(path);
  if (!(await file.exists())) throw new Error(`There's no photo at ${path}.`);
  // Bun doesn't know iPhone photos' type from the file name.
  const mimeType = path.toLowerCase().endsWith(".heic") ? "image/heic" : file.type;
  const photo = { fileName: basename(path), mimeType, bytes: Buffer.from(await file.arrayBuffer()) };
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

function printEntry(entry: ChatEntry): void {
  console.log(`[${entry.id}] ${entry.from}: ${entry.text}`);
}

function describeSeededTrip(trip: TripSummary): string {
  if (trip.open_poll) {
    const options = trip.open_poll.options.map(
      (option, index) =>
        `  ${index + 1}. ${option.name} (~$${option.estimated_cost_per_person_usd}/person)`,
    );
    return ["The destination poll is open. Members vote by number:", ...options].join("\n");
  }
  const dates = trip.dates ? `, ${trip.dates.start} to ${trip.dates.end}` : "";
  return `The destination is chosen: ${trip.destination}${dates}.`;
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

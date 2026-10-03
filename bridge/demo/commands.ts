// Sets up the demo group on scout's Linq line: get the demo phones ready, make
// a rehearsal group, and reset the demo group's trip between rehearsals. These
// send real iMessages to the phones in demo/roster.json. See DEVELOPING.md.

import { LINQ_API_URL } from "../linq-api";
import { scoutUrl } from "../scout";
import { resetTrip } from "../devchat/trips";
import { openContactList } from "./contacts";
import { createRehearsalGroup, findDemoGroups } from "./groups";
import { findScoutNumber, listChats, type DemoLine } from "./line";
import { loadRoster } from "./roster";
import { setUpPhones, type PhoneSetup, type SetupReport } from "./setup";

const USAGE = `Usage (from bridge/, with LINQ_API_KEY in bridge/.env and the phones in demo/roster.json):
  bun run demo setup   add the phones as contacts, show who has texted scout, and send them scout's contact card
  bun run demo group   make a fresh rehearsal group of every phone plus scout
  bun run demo reset   clear the newest demo group's trip, so the journey can run again (needs the scout service)`;

try {
  await runCommand(process.argv[2]);
} catch (error) {
  console.error(describeError(error));
  process.exitCode = 1;
}

async function runCommand(command: string | undefined): Promise<void> {
  switch (command) {
    case "setup":
      return setUp();
    case "group":
      return makeRehearsalGroup();
    case "reset":
      return resetDemoGroup();
    default:
      throw new Error(USAGE);
  }
}

async function setUp(): Promise<void> {
  const roster = await loadRoster();
  const line = await connectToDemoLine();
  const report = await setUpPhones(roster, line, await openContactList());
  printSetupReport(line.scoutNumber, report);
}

async function makeRehearsalGroup(): Promise<void> {
  const roster = await loadRoster();
  const group = await createRehearsalGroup(await connectToDemoLine(), roster);
  console.log(`Made "${group.display_name}" (${group.id}) with ${roster.map(({ name }) => name).join(", ")}.`);
  console.log("To rehearse in it again, reset its trip: bun run demo reset");
}

async function resetDemoGroup(): Promise<void> {
  const roster = await loadRoster();
  const [group] = findDemoGroups(await listChats(await connectToDemoLine()), roster);
  if (!group) {
    throw new Error(
      "scout isn't in a group of the demo phones yet. Make one with bun run demo group, or add scout to one in Messages.",
    );
  }
  await resetTrip(group.id);
  console.log(`Reset "${group.display_name}" (${group.id}). Its next message starts over with scout's introduction.`);
}

async function connectToDemoLine(): Promise<DemoLine> {
  const apiKey = process.env.LINQ_API_KEY;
  if (!apiKey) throw new Error("Set LINQ_API_KEY in bridge/.env to the demo line's key.");
  const api = { apiKey, apiUrl: LINQ_API_URL };
  return { api, scoutNumber: await findScoutNumber(api) };
}

function printSetupReport(scoutNumber: string, { isCardActive, phones }: SetupReport): void {
  console.log(`scout's number: ${scoutNumber}`);
  if (!isCardActive) {
    console.log("scout's contact card is new, and Linq is still applying it. Run this again in a minute to send it.");
  }
  console.log("");
  const nameWidth = Math.max(...phones.map(({ phone }) => phone.name.length));
  for (const setup of phones) {
    const mark = setup.hasTexted ? "✓" : "✗";
    console.log(`  ${mark} ${setup.phone.name.padEnd(nameWidth)}  ${setup.phone.phone}  ${describePhone(setup)}`);
  }

  const waiting = phones.filter((setup) => !setup.hasTexted).length;
  console.log("");
  if (waiting === 0) {
    console.log("Every phone has texted scout. Make a rehearsal group with bun run demo group.");
    return;
  }
  console.log(`${phones.length - waiting} of ${phones.length} phones have texted scout.`);
  console.log(`From each ✗ phone, text ${scoutNumber} once (anything, like "hi"), then run this again.`);
}

function describePhone(setup: PhoneSetup): string {
  const done: string[] = [];
  if (setup.isNewContact) done.push("added as a contact");
  if (!setup.hasTexted) return [...done, "hasn't texted scout yet"].join(", ");
  done.push("texted scout");
  if (setup.wasGreeted) done.push("scout said hi");
  if (setup.wasSentCard) done.push("sent scout's contact card");
  return done.join(", ");
}

function describeError(error: unknown): string {
  if (error instanceof Error && "code" in error && error.code === "ConnectionRefused") {
    return `Couldn't reach scout at ${scoutUrl()}. Start it first: uv run --env-file .env scout-server`;
  }
  return error instanceof Error ? error.message : String(error);
}

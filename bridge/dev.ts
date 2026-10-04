// Starts everything scout needs in one terminal, with each line labeled: the
// Python service, the bridge, in Linq mode the relay that brings Linq's events
// to this Mac, and the ngrok tunnel that serves calendar links when
// SCOUT_PUBLIC_URL is set. It checks the settings first, and Ctrl-C stops them all.
//
//   cd bridge && bun run dev

import { join } from "node:path";
import { findSetupProblems, iMessageMode, isTunnelStatus, publicDomain, type DevSetup } from "./dev-setup";
import { readEnvFile } from "./env-file";
import { WEBHOOK_PORT, WEBHOOK_URL } from "./linq";
import { isWorthShowing } from "./relay-log";
import { stopAfterCtrlC, stopChildren } from "./shutdown";

const BRIDGE_FOLDER = import.meta.dir;
const REPO_ROOT = join(BRIDGE_FOLDER, "..");
const DEFAULT_SERVICE_PORT = 8787;

type Labeled = { label: string; subprocess: Bun.Subprocess<"ignore", "pipe", "pipe"> };
type LineFilter = (line: string) => boolean;
const showEveryLine: LineFilter = () => true;

const setup = await describeSetup();
const problems = findSetupProblems(setup);
if (problems.length > 0) {
  console.error("Fix these first:");
  for (const problem of problems) console.error(`  ✗ ${problem}`);
  process.exit(1);
}

const mode = iMessageMode(setup);
const running: Labeled[] = [
  start("service", ["uv", "run", "--env-file", ".env", "scout-server"], REPO_ROOT),
  start("bridge", [process.execPath, "index.ts"], BRIDGE_FOLDER),
];
if (mode === "linq") {
  running.push(
    start("relay", ["linq", "webhooks", "listen", "--forward-to", WEBHOOK_URL], BRIDGE_FOLDER, isWorthShowing),
  );
}
const calendarDomain = publicDomain(setup.serviceSettings);
if (calendarDomain) {
  // Only /calendars/* gets through the tunnel; the service refuses the rest.
  running.push(
    start("tunnel", ["ngrok", "http", `--url=${calendarDomain}`, String(servicePort(setup.serviceSettings)), "--log=stdout"], BRIDGE_FOLDER, isTunnelStatus),
  );
}
console.log(`[dev] scout is starting in ${mode} mode. Ctrl-C stops everything.`);

let isStopping = false;
process.on("SIGINT", () => stopAll(0, stopAfterCtrlC));
process.on("SIGTERM", () => stopAll(0));
for (const { label, subprocess } of running) {
  // One piece stopping (a crash, a bad key) takes the others down with it, so
  // nobody debugs a bridge whose service is gone.
  subprocess.exited.then((exitCode) => {
    if (isStopping) return;
    console.error(`[dev] the ${label} stopped (exit code ${exitCode}), so everything is stopping.`);
    stopAll(1);
  });
}

async function describeSetup(): Promise<DevSetup> {
  const bridgeSettings = process.env;
  const serviceSettings = await readEnvFile(join(REPO_ROOT, ".env"));
  const isLinq = iMessageMode({ bridgeSettings }) === "linq";
  const installed = { uv: Bun.which("uv") !== null, linq: Bun.which("linq") !== null, ngrok: Bun.which("ngrok") !== null };

  const ports = [
    { port: servicePort(serviceSettings), usedBy: "the scout service" },
    ...(isLinq ? [{ port: WEBHOOK_PORT, usedBy: "the bridge's Linq webhook" }] : []),
  ];
  return {
    isMac: process.platform === "darwin",
    serviceSettings,
    bridgeSettings,
    installed,
    linqLoggedIn: isLinq && installed.linq ? await isLinqLoggedIn() : null,
    busyPorts: ports.filter(({ port }) => isPortBusy(port)),
  };
}

function servicePort(serviceSettings: DevSetup["serviceSettings"]): number {
  return Number(serviceSettings?.SCOUT_PORT || DEFAULT_SERVICE_PORT);
}

async function isLinqLoggedIn(): Promise<boolean> {
  const whoami = Bun.spawn(["linq", "whoami"], { stdout: "ignore", stderr: "ignore" });
  return (await whoami.exited) === 0;
}

function isPortBusy(port: number): boolean {
  try {
    Bun.serve({ hostname: "127.0.0.1", port, fetch: () => new Response() }).stop(true);
    return false;
  } catch {
    return true;
  }
}

function start(label: string, command: string[], cwd: string, shouldShow = showEveryLine): Labeled {
  const subprocess = Bun.spawn(command, { cwd, stdin: "ignore", stdout: "pipe", stderr: "pipe" });
  const prefix = `[${label}]`.padEnd("[service]".length);
  printLines(subprocess.stdout, (line) => shouldShow(line) && console.log(`${prefix} ${line}`));
  // Errors always show.
  printLines(subprocess.stderr, (line) => console.error(`${prefix} ${line}`));
  return { label, subprocess };
}

async function printLines(stream: ReadableStream<Uint8Array>, print: (line: string) => void): Promise<void> {
  const decoder = new TextDecoder();
  let unfinishedLine = "";
  for await (const chunk of stream) {
    const lines = (unfinishedLine + decoder.decode(chunk, { stream: true })).split("\n");
    unfinishedLine = lines.pop() ?? "";
    for (const line of lines) print(line);
  }
  if (unfinishedLine) print(unfinishedLine);
}

async function stopAll(exitCode: number, stop = stopChildren): Promise<void> {
  if (isStopping) return;
  isStopping = true;
  if (mode === "linq") {
    // A second Ctrl-C would leave the relay's webhook behind (see shutdown.ts).
    console.log("[dev] stopping. The relay is deleting its Linq webhook, so don't press Ctrl-C again.");
  }
  await stop(running.map(({ subprocess }) => subprocess));
  process.exit(exitCode);
}

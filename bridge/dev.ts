// Starts everything scout needs in one terminal, with each line labeled: the
// Python service, the bridge, and in Linq mode the relay that brings Linq's
// events to this Mac. It checks the settings first, and Ctrl-C stops them all.
//
//   cd bridge && bun run dev

import { join } from "node:path";
import { findSetupProblems, iMessageMode, type DevSetup } from "./dev-setup";
import { readEnvFile } from "./env-file";
import { WEBHOOK_PORT, WEBHOOK_URL } from "./linq";

const BRIDGE_FOLDER = import.meta.dir;
const REPO_ROOT = join(BRIDGE_FOLDER, "..");
const DEFAULT_SERVICE_PORT = 8787;

type Labeled = { label: string; subprocess: Bun.Subprocess<"ignore", "pipe", "pipe"> };

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
  running.push(start("relay", ["linq", "webhooks", "listen", "--forward-to", WEBHOOK_URL], BRIDGE_FOLDER));
}
console.log(`[dev] scout is starting in ${mode} mode. Ctrl-C stops everything.`);

let isStopping = false;
process.on("SIGINT", () => stopAll(0));
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
  const installed = { uv: Bun.which("uv") !== null, linq: Bun.which("linq") !== null };

  const ports = [
    { port: Number(serviceSettings?.SCOUT_PORT || DEFAULT_SERVICE_PORT), usedBy: "the scout service" },
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

function start(label: string, command: string[], cwd: string): Labeled {
  const subprocess = Bun.spawn(command, { cwd, stdin: "ignore", stdout: "pipe", stderr: "pipe" });
  const prefix = `[${label}]`.padEnd("[service]".length);
  printLines(subprocess.stdout, prefix, (line) => console.log(line));
  printLines(subprocess.stderr, prefix, (line) => console.error(line));
  return { label, subprocess };
}

async function printLines(
  stream: ReadableStream<Uint8Array>,
  prefix: string,
  print: (line: string) => void,
): Promise<void> {
  const decoder = new TextDecoder();
  let unfinishedLine = "";
  for await (const chunk of stream) {
    const lines = (unfinishedLine + decoder.decode(chunk, { stream: true })).split("\n");
    unfinishedLine = lines.pop() ?? "";
    for (const line of lines) print(`${prefix} ${line}`);
  }
  if (unfinishedLine) print(`${prefix} ${unfinishedLine}`);
}

async function stopAll(exitCode: number): Promise<void> {
  if (isStopping) return;
  isStopping = true;
  for (const { subprocess } of running) subprocess.kill();
  await Promise.all(running.map(({ subprocess }) => subprocess.exited));
  process.exit(exitCode);
}

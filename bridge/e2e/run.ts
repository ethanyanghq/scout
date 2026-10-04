// The end-to-end tests: plays every console script in this folder against a
// throwaway scout service, through the real bridge. They cover the critical
// user journeys in AGENTS.md.
//
//   cd bridge && bun run e2e                          every script
//   cd bridge && bun run e2e votes-and-winner.chat    one script
//
// Needs uv, and ANTHROPIC_API_KEY (or OPENAI_API_KEY) in the repo's .env:
// most journeys go through the AI, which takes about 10 seconds a message
// and costs tokens.

import { openSync } from "node:fs";
import { mkdir, readdir, rm } from "node:fs/promises";
import { join } from "node:path";
import { readEnvFile } from "../env-file";

const E2E_FOLDER = import.meta.dir;
const BRIDGE_FOLDER = join(E2E_FOLDER, "..");
const REPO_ROOT = join(BRIDGE_FOLDER, "..");
// Inside bridge/.devchat, which git ignores.
const RUN_FOLDER = join(BRIDGE_FOLDER, ".devchat", "e2e");
// Both are kept after a run, to look into failures.
const SERVICE_LOG = join(RUN_FOLDER, "service.log");
const DATABASE = join(RUN_FOLDER, "scout.db");
const MEDIA_FOLDER = join(RUN_FOLDER, "media");
const SERVICE_START_TIMEOUT_MS = 30_000;

const scripts = await chooseScripts(process.argv.slice(2));
await warnIfAiIsMissing();
await mkdir(RUN_FOLDER, { recursive: true });
const port = findFreePort();
const service = await startService(port);

const failed: string[] = [];
try {
  for (const script of scripts) {
    console.log(`\n── ${script}`);
    if (!(await runScript(script, port))) failed.push(script);
  }
} finally {
  service.kill();
  await service.exited;
}

console.log(`\n${scripts.length - failed.length} of ${scripts.length} scripts passed.`);
if (failed.length > 0) {
  console.log(`Failed: ${failed.join(", ")}. The service's log and database are in ${RUN_FOLDER}.`);
  process.exitCode = 1;
}

async function chooseScripts(requested: string[]): Promise<string[]> {
  if (requested.length > 0) return requested;
  const files = await readdir(E2E_FOLDER);
  return files.filter((file) => file.endsWith(".chat")).sort();
}

async function warnIfAiIsMissing(): Promise<void> {
  const settings = await readEnvFile(join(REPO_ROOT, ".env"));
  const keyNames = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"];
  if (keyNames.some((name) => process.env[name] || settings?.[name])) return;
  console.warn("Neither ANTHROPIC_API_KEY nor OPENAI_API_KEY is set in .env, so scripts that need the AI will fail.");
}

function findFreePort(): number {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response() });
  const port = probe.port!;
  probe.stop(true);
  return port;
}

// A fresh database and media folder each run, so scripts never see a
// developer's trips.
async function startService(port: number) {
  await rm(DATABASE, { force: true });
  await rm(MEDIA_FOLDER, { recursive: true, force: true });
  const envFile = (await Bun.file(join(REPO_ROOT, ".env")).exists()) ? ["--env-file", ".env"] : [];
  const log = openSync(SERVICE_LOG, "w");
  const service = Bun.spawn(["uv", "run", ...envFile, "scout-server"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      SCOUT_PORT: String(port),
      SCOUT_PUBLIC_URL: `http://127.0.0.1:${port}`,
      SCOUT_DB_PATH: DATABASE,
      SCOUT_MEDIA_DIR: MEDIA_FOLDER,
    },
    stdout: log,
    stderr: log,
  });
  await waitUntilServing(port, service);
  return service;
}

async function waitUntilServing(port: number, service: Bun.Subprocess): Promise<void> {
  const deadline = Date.now() + SERVICE_START_TIMEOUT_MS;
  while (Date.now() < deadline) {
    if (service.exitCode !== null) {
      throw new Error(`The scout service stopped while starting. See ${SERVICE_LOG}.`);
    }
    try {
      await fetch(`http://127.0.0.1:${port}/dev/trips/ready-check`);
      return;
    } catch {
      await Bun.sleep(200);
    }
  }
  service.kill();
  throw new Error(`The scout service didn't start within 30 seconds. See ${SERVICE_LOG}.`);
}

async function runScript(script: string, port: number): Promise<boolean> {
  const run = Bun.spawn(
    [process.execPath, "devchat/commands.ts", "run", join(E2E_FOLDER, script)],
    {
      cwd: BRIDGE_FOLDER,
      env: { ...process.env, SCOUT_URL: `http://127.0.0.1:${port}` },
      stdout: "inherit",
      stderr: "inherit",
    },
  );
  return (await run.exited) === 0;
}

// What `bun run dev` checks before starting anything, so a missing key or a
// logged-out Linq CLI shows up at once instead of when the first text fails.

export type DevSetup = {
  isMac: boolean;
  // The service's .env, or null when the file doesn't exist.
  serviceSettings: Record<string, string> | null;
  // What the bridge will see: bridge/.env (which Bun loads) and the shell.
  bridgeSettings: Record<string, string | undefined>;
  installed: { uv: boolean; linq: boolean };
  // Only checked in Linq mode, with the CLI installed.
  linqLoggedIn: boolean | null;
  busyPorts: { port: number; usedBy: string }[];
};

export function iMessageMode(setup: Pick<DevSetup, "bridgeSettings">): string {
  return setup.bridgeSettings.IMESSAGE_MODE ?? "local";
}

// Returns one line per problem, each saying how to fix it.
export function findSetupProblems(setup: DevSetup): string[] {
  const problems: string[] = [];
  if (!setup.installed.uv) {
    problems.push("Install uv, which runs the scout service: https://docs.astral.sh/uv/");
  }
  if (!setup.serviceSettings) {
    problems.push("Create the service's settings: cp .env.example .env, then fill in ANTHROPIC_API_KEY.");
  } else if (!setup.serviceSettings.ANTHROPIC_API_KEY && !setup.serviceSettings.OPENAI_API_KEY) {
    problems.push("Set ANTHROPIC_API_KEY (or OPENAI_API_KEY) in .env.");
  }
  problems.push(...findModeProblems(setup));
  for (const { port, usedBy } of setup.busyPorts) {
    problems.push(`Port ${port} (${usedBy}) is already in use. Is scout already running?`);
  }
  return problems;
}

function findModeProblems(setup: DevSetup): string[] {
  const mode = iMessageMode(setup);
  switch (mode) {
    case "linq":
      return findLinqProblems(setup);
    case "cloud":
      return ["PHOTON_PROJECT_ID", "PHOTON_PROJECT_SECRET"]
        .filter((name) => !setup.bridgeSettings[name])
        .map((name) => `Set ${name} in bridge/.env (from your Photon project).`);
    case "local":
      return setup.isMac
        ? []
        : ["Local mode needs a Mac signed into Messages. For a Linq line, set IMESSAGE_MODE=linq in bridge/.env."];
    default:
      return [`IMESSAGE_MODE in bridge/.env must be local, cloud or linq, not "${mode}".`];
  }
}

function findLinqProblems(setup: DevSetup): string[] {
  const problems: string[] = [];
  if (!setup.bridgeSettings.LINQ_API_KEY) {
    problems.push("Set LINQ_API_KEY in bridge/.env (from `linq signup` or the Linq dashboard).");
  }
  if (!setup.installed.linq) {
    problems.push("Install the Linq CLI, which relays Linq's events here: npm i -g @linqapp/cli");
  } else if (setup.linqLoggedIn === false) {
    problems.push("Log the Linq CLI in: linq login (or linq signup for a new line).");
  }
  return problems;
}

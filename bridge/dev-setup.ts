// What `bun run dev` checks before starting anything, so a missing key or a
// logged-out Linq CLI shows up at once instead of when the first text fails.

export type DevSetup = {
  isMac: boolean;
  // The service's .env, or null when the file doesn't exist.
  serviceSettings: Record<string, string> | null;
  // What the bridge will see: bridge/.env (which Bun loads) and the shell.
  bridgeSettings: Record<string, string | undefined>;
  installed: { uv: boolean; linq: boolean; ngrok: boolean };
  // Only checked in Linq mode, with the CLI installed.
  linqLoggedIn: boolean | null;
  busyPorts: { port: number; usedBy: string }[];
};

// The domain scout's calendar links are served from, taken from the service's
// SCOUT_PUBLIC_URL, or null when it isn't set.
export function publicDomain(serviceSettings: DevSetup["serviceSettings"]): string | null {
  const publicUrl = serviceSettings?.SCOUT_PUBLIC_URL;
  return publicUrl ? new URL(publicUrl).hostname : null;
}

// ngrok prints a line for every request it forwards; only its start and its
// problems are worth showing.
export function isTunnelStatus(ngrokLine: string): boolean {
  return ngrokLine.includes("started tunnel") || /lvl=(warn|eror|crit)/.test(ngrokLine);
}

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
  problems.push(...findTunnelProblems(setup));
  problems.push(...findModeProblems(setup));
  for (const { port, usedBy } of setup.busyPorts) {
    problems.push(`Port ${port} (${usedBy}) is already in use. Is scout already running?`);
  }
  return problems;
}

function findTunnelProblems(setup: DevSetup): string[] {
  const publicUrl = setup.serviceSettings?.SCOUT_PUBLIC_URL;
  if (!publicUrl) return [];
  if (!URL.canParse(publicUrl)) {
    return [`SCOUT_PUBLIC_URL in .env must be a full address like https://your-name.ngrok-free.dev, not "${publicUrl}".`];
  }
  if (!setup.installed.ngrok) {
    return ["Install ngrok, which makes the calendar links public: brew install ngrok, then ngrok config add-authtoken <token>."];
  }
  return [];
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

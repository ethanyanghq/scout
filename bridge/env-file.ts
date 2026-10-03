// Reads the settings in an env file (the service's .env or bridge/.env), so
// developer tools can check them before starting anything.

export async function readEnvFile(path: string): Promise<Record<string, string> | null> {
  const file = Bun.file(path);
  if (!(await file.exists())) return null;

  const settings: Record<string, string> = {};
  for (const line of (await file.text()).split("\n")) {
    const match = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (match) settings[match[1]!] = unquote(match[2]!);
  }
  return settings;
}

function unquote(value: string): string {
  const quoted = value.match(/^(["'])(.*)\1$/);
  return quoted ? quoted[2]! : value;
}

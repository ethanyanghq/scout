// The console's current chat, saved between commands so each command can run
// on its own. AI agents drive the console one shell command at a time.

import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import type { ChatEntry, ChatMember } from "./platform";

const SESSION_FILE = join(import.meta.dir, "..", ".devchat", "session.json");

export type Session = { chatId: string; members: ChatMember[]; transcript: ChatEntry[] };

export async function loadSession(): Promise<Session> {
  const file = Bun.file(SESSION_FILE);
  if (!(await file.exists())) {
    throw new Error("There's no console chat yet. Start one: bun run devchat start maya leo priya");
  }
  return (await file.json()) as Session;
}

export async function saveSession(session: Session): Promise<void> {
  await mkdir(dirname(SESSION_FILE), { recursive: true });
  await Bun.write(SESSION_FILE, JSON.stringify(session, null, 2));
}

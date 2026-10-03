// Connects scout's Python service to iMessage through Photon's Spectrum SDK.
//
// Photon can only send messages from TypeScript, so this bridge stays thin:
// it forwards each incoming text to scout over HTTP and sends back whatever
// scout replies. All of scout's logic lives in the Python service.
//
// Run with:  bun run index.ts
// Settings (Bun reads them from bridge/.env automatically):
//   IMESSAGE_MODE=local           Use this Mac's Messages account (no Photon plan).
//                                 Also set SCOUT_GROUP_NAME: the one group chat
//                                 scout may read and reply in.
//   IMESSAGE_MODE=cloud           Use a Photon cloud line; also set
//                                 PHOTON_PROJECT_ID and PHOTON_PROJECT_SECRET.
//   SCOUT_URL=http://127.0.0.1:8787   Where the Python service is listening.

import { Spectrum, UnsupportedError, type Message, type Space } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { localIMessage } from "@spectrum-ts/imessage-local";
import { IMessageSDK } from "@photon-ai/imessage-kit";

const SCOUT_URL = process.env.SCOUT_URL ?? "http://127.0.0.1:8787";

type IncomingText = {
  space_id: string;
  sender_phone: string;
  text: string;
  sent_at: string;
  participant_phones: string[];
};

const mode = process.env.IMESSAGE_MODE ?? "local";
const isScoutChat = await decideWhichChatsScoutJoins(mode);
const app = await connectToIMessage(mode);
console.log(`scout bridge is listening for texts, forwarding to ${SCOUT_URL}`);

// Messages are handled one at a time, on purpose: scout finishes replying to
// one text before it reads the next, so its view of the trip is never stale.
for await (const [space, message] of app.messages) {
  if (message.direction === "outbound") continue;
  // Phase 1 only understands text. Photos and receipts arrive in Phase 2.
  if (message.content.type !== "text" || !message.sender) continue;

  // Every other chat is dropped here, before scout or Claude sees any of it.
  if (!isScoutChat(space)) continue;

  try {
    const replies = await askScout({
      space_id: space.id,
      sender_phone: message.sender.id,
      text: message.content.text,
      sent_at: message.timestamp.toISOString(),
      participant_phones: await listParticipants(space, message),
    });
    for (const reply of replies) {
      await space.send(reply);
    }
  } catch (error) {
    // Keep listening: one failed message shouldn't take scout offline.
    console.error(`Couldn't handle message ${message.id} in ${space.id}:`, error);
  }
}

async function connectToIMessage(mode: string) {
  if (mode === "local") {
    return Spectrum({ providers: [localIMessage.config()] });
  }
  if (mode === "cloud") {
    return Spectrum({
      projectId: requireSetting("PHOTON_PROJECT_ID"),
      projectSecret: requireSetting("PHOTON_PROJECT_SECRET"),
      providers: [imessage.config()],
    });
  }
  throw new Error(`IMESSAGE_MODE must be "local" or "cloud", got "${mode}"`);
}

async function askScout(text: IncomingText): Promise<string[]> {
  const response = await fetch(`${SCOUT_URL}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text),
  });
  if (!response.ok) {
    throw new Error(`scout returned ${response.status}: ${await response.text()}`);
  }
  const { replies } = (await response.json()) as { replies: string[] };
  return replies;
}

// In local mode the Mac's Messages account may be a real person's, so scout is
// locked to the one group named in SCOUT_GROUP_NAME. A cloud line belongs to
// scout alone, so there it plans in any group but never in one-on-one chats.
async function decideWhichChatsScoutJoins(mode: string): Promise<(space: Space) => boolean> {
  if (mode !== "local") {
    return (space) => imessage.is(space) && imessage(space).type === "group";
  }
  const groupName = requireSetting("SCOUT_GROUP_NAME");
  const groupId = await findGroupChatId(groupName);
  console.log(`scout will only read and reply in "${groupName}"`);
  return (space) => space.id === groupId;
}

async function findGroupChatId(name: string): Promise<string> {
  const messages = new IMessageSDK();
  try {
    const chats = await messages.listChats({ search: name, kind: "group" });
    const matches = chats.filter((chat) => chat.name === name);
    const [match] = matches;
    if (matches.length !== 1 || !match) {
      throw new Error(
        `Expected exactly one group chat named "${name}" in Messages, found ${matches.length}. ` +
          "Check SCOUT_GROUP_NAME matches the group's name exactly.",
      );
    }
    return match.chatId;
  } finally {
    await messages.close();
  }
}

// Lets scout count group members who haven't texted yet. Only cloud group
// chats can list members; everywhere else scout learns who's in the group as
// people text, so an empty list is expected there.
async function listParticipants(space: Space, message: Message): Promise<string[]> {
  if (message.platform !== "imessage" || imessage(space).type !== "group") {
    return [];
  }
  try {
    const members = await space.getMembers();
    return members.map((member) => member.id);
  } catch (error) {
    // Photon's shared-pool lines can't list group members.
    if (error instanceof UnsupportedError) return [];
    throw error;
  }
}

function requireSetting(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} in bridge/.env`);
  return value;
}

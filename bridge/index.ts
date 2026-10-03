// Connects scout's Python service to iMessage through Photon's Spectrum SDK.
//
// Photon can only send messages from TypeScript, so this bridge stays thin:
// it forwards each incoming text (and photo, such as a receipt) to scout over
// HTTP and sends back whatever scout replies. All of scout's logic lives in the Python service.
//
// Run with:  bun run index.ts
// Settings (Bun reads them from bridge/.env automatically):
//   IMESSAGE_MODE=local           Use this Mac's Messages account (no Photon plan).
//   IMESSAGE_MODE=cloud           Use a Photon cloud line; also set
//                                 PHOTON_PROJECT_ID and PHOTON_PROJECT_SECRET.
//   SCOUT_URL=http://127.0.0.1:8787   Where the Python service is listening.

import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { $ } from "bun";
import {
  Spectrum,
  UnsupportedError,
  type Content,
  type Message,
  type Space,
} from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { localIMessage } from "@spectrum-ts/imessage-local";

const SCOUT_URL = process.env.SCOUT_URL ?? "http://127.0.0.1:8787";
// Claude reads images up to about this many pixels on the long side; bigger
// photos only cost more to send.
const MAX_PHOTO_EDGE_PIXELS = 1568;

type IncomingPhoto = {
  media_type: "image/jpeg";
  base64_data: string;
};

type IncomingText = {
  space_id: string;
  sender_phone: string;
  text: string;
  sent_at: string;
  participant_phones: string[];
  photo: IncomingPhoto | null;
};

type PhotoAttachment = Extract<Content, { type: "attachment" }>;

// What scout can use from one message: its words and its first photo.
type ReadableParts = { text: string; photo: PhotoAttachment | null };

const app = await connectToIMessage(process.env.IMESSAGE_MODE ?? "local");
console.log(`scout bridge is listening for texts, forwarding to ${SCOUT_URL}`);

// Messages are handled one at a time, on purpose: scout finishes replying to
// one text before it reads the next, so its view of the trip is never stale.
for await (const [space, message] of app.messages) {
  if (message.direction === "outbound") continue;
  if (!message.sender) continue;
  if (isLocalDirectMessage(space)) continue;
  // Reactions, typing indicators, and the like aren't for scout.
  const parts = readableParts(message.content);
  if (!parts) continue;

  try {
    const replies = await askScout({
      space_id: space.id,
      sender_phone: message.sender.id,
      text: parts.text,
      sent_at: message.timestamp.toISOString(),
      participant_phones: await listParticipants(space, message),
      photo: parts.photo ? await toJpeg(parts.photo) : null,
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

// In local mode the bridge runs on scout's own Apple ID, which exists only to
// sit in group chats. Private chats with scout go through the Photon line
// instead (see scout-imessage-groups.md), so a direct text to this account
// must not start a trip. Cloud mode still answers one-on-one texts.
function isLocalDirectMessage(space: Space): boolean {
  return localIMessage.is(space) && localIMessage(space).type === "dm";
}

// A photo sent with a caption arrives as a group of a text and an attachment.
function readableParts(content: Content): ReadableParts | null {
  if (content.type === "text") return { text: content.text, photo: null };
  if (isPhoto(content)) return { text: "", photo: content };
  if (content.type !== "group") return null;

  const items = content.items.map((item) => item.content);
  const text = items.find((item) => item.type === "text");
  const photo = items.find(isPhoto);
  if (!text && !photo) return null;
  return {
    text: text?.type === "text" ? text.text : "",
    photo: photo ?? null,
  };
}

function isPhoto(content: Content): content is PhotoAttachment {
  return content.type === "attachment" && content.mimeType.startsWith("image/");
}

// iPhones send HEIC, which Claude can't read, so every photo goes through
// macOS's built-in `sips` to become a downsized JPEG.
async function toJpeg(photo: PhotoAttachment): Promise<IncomingPhoto> {
  const folder = await mkdtemp(join(tmpdir(), "scout-photo-"));
  try {
    // sips reads the format from the file's contents, so the name doesn't matter.
    const original = join(folder, "original");
    const converted = join(folder, "photo.jpg");
    await writeFile(original, await photo.read());
    await $`sips -s format jpeg -Z ${MAX_PHOTO_EDGE_PIXELS} ${original} --out ${converted}`.quiet();
    const jpeg = await readFile(converted);
    return { media_type: "image/jpeg", base64_data: jpeg.toString("base64") };
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
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

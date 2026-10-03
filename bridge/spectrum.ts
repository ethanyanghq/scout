// Relays messages from any Spectrum provider (Photon's iMessage lines today)
// to scout and sends scout's replies back to the same chat.

import {
  UnsupportedError,
  type Content,
  type Message,
  type Space,
  type SpectrumInstance,
} from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { localIMessage } from "@spectrum-ts/imessage-local";
import { askScout, toJpeg } from "./scout";
import { secondsSince, type MessageOutcome, type Skipped } from "./trace";

type PhotoAttachment = Extract<Content, { type: "attachment" }>;

// What scout can use from one message: its words and its first photo.
type ReadableParts = { text: string; photo: PhotoAttachment | null };
type ScoutMessage = ReadableParts & { senderPhone: string };

export async function relaySpectrumMessages(
  app: SpectrumInstance,
  reportOutcome: (outcome: MessageOutcome) => void,
): Promise<void> {
  // Messages are handled one at a time, on purpose: scout finishes replying to
  // one text before it reads the next, so its view of the trip is never stale.
  for await (const [space, message] of app.messages) {
    const startedAt = performance.now();
    const outcome = { id: message.id, chatId: space.id };
    const readable = readForScout(space, message);
    if ("skipReason" in readable) {
      reportOutcome({ ...outcome, kind: "skipped", reason: readable.skipReason });
      continue;
    }

    try {
      const replies = await askScout({
        space_id: space.id,
        sender_phone: readable.senderPhone,
        text: readable.text,
        sent_at: message.timestamp.toISOString(),
        participant_phones: await listParticipants(space, message),
        photo: readable.photo ? await toJpeg(await readable.photo.read()) : null,
      });
      for (const reply of replies) {
        await space.send(reply);
      }
      reportOutcome({
        ...outcome,
        kind: "handled",
        replyCount: replies.length,
        seconds: secondsSince(startedAt),
      });
    } catch (error) {
      // Keep listening: one failed message shouldn't take scout offline.
      reportOutcome({ ...outcome, kind: "failed", error });
    }
  }
}

function readForScout(space: Space, message: Message): ScoutMessage | Skipped {
  if (message.direction === "outbound") return { skipReason: "scout's own message" };
  if (!message.sender) return { skipReason: "no sender" };
  if (isLocalDirectMessage(space)) {
    return { skipReason: "a private chat with scout's local account" };
  }
  // Reactions, typing indicators, and the like aren't for scout.
  const parts = readableParts(message.content);
  if (!parts) return { skipReason: `nothing scout can read (${message.content.type})` };
  return { ...parts, senderPhone: message.sender.id };
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

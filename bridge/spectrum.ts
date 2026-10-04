// Relays messages from any Spectrum provider (Photon's iMessage lines today)
// to scout and sends scout's replies back to the same chat.

import {
  UnsupportedError,
  custom,
  reaction,
  reply,
  richlink,
  type Content,
  type ContentInput,
  type Message,
  type Space,
  type SpectrumInstance,
} from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import z from "zod";
import { localIMessage } from "@spectrum-ts/imessage-local";
import { askScout, tellScoutAboutTapback, toJpeg, type ScoutAction } from "./scout";
import { tapbackEmoji, tapbackNamed } from "./tapbacks";
import { secondsSince, type MessageOutcome, type Skipped } from "./trace";

type PhotoAttachment = Extract<Content, { type: "attachment" }>;

// What scout can use from one message: its words and its first photo.
type ReadableParts = { text: string; photo: PhotoAttachment | null };
type ScoutMessage = ReadableParts & {
  kind: "message";
  senderPhone: string;
  replyToId: string | null;
};
type ScoutTapback = { kind: "tapback"; senderPhone: string; tapback: string; targetId: string };

// Spectrum reacts and replies to a Message, not an ID, so the relay keeps the
// messages it has seen and sent lately. Older ones, and everything from before
// a restart, get scout's plain-text fallback instead.
const REMEMBERED_MESSAGES = 1000;

export async function relaySpectrumMessages(
  app: SpectrumInstance,
  reportOutcome: (outcome: MessageOutcome) => void,
): Promise<void> {
  const recent = new RecentMessages();
  // Messages are handled one at a time, on purpose: scout finishes replying to
  // one text before it reads the next, so its view of the trip is never stale.
  for await (const [space, message] of app.messages) {
    recent.remember(message);
    const startedAt = performance.now();
    const outcome = { id: message.id, chatId: space.id };
    const readable = readForScout(space, message);
    if ("skipReason" in readable) {
      reportOutcome({ ...outcome, kind: "skipped", reason: readable.skipReason });
      continue;
    }

    try {
      const actions =
        readable.kind === "tapback"
          ? await tellScoutAboutTapback({
              space_id: space.id,
              sender_phone: readable.senderPhone,
              tapback: readable.tapback,
              message_id: readable.targetId,
              message_text: await findText(space, readable.targetId, recent),
              sent_at: message.timestamp.toISOString(),
            })
          : await askScout({
              space_id: space.id,
              sender_phone: readable.senderPhone,
              text: readable.text,
              sent_at: message.timestamp.toISOString(),
              participant_phones: await listParticipants(space, message),
              photo: readable.photo ? await toJpeg(await readable.photo.read()) : null,
              message_id: message.id,
              reply_to_text: readable.replyToId
                ? await findText(space, readable.replyToId, recent)
                : null,
            });
      for (const action of actions) {
        await perform(space, action, recent);
      }
      reportOutcome({
        ...outcome,
        kind: "handled",
        replyCount: actions.length,
        seconds: secondsSince(startedAt),
      });
    } catch (error) {
      // Keep listening: one failed message shouldn't take scout offline.
      reportOutcome({ ...outcome, kind: "failed", error });
    }
  }
}

async function perform(space: Space, action: ScoutAction, recent: RecentMessages): Promise<void> {
  switch (action.type) {
    case "say": {
      const thread = action.reply_to ? await findMessage(space, action.reply_to, recent) : undefined;
      await sendOrFallBack(space, thread ? reply(action.text, thread) : null, action.text, recent);
      return;
    }
    case "react": {
      const target = recent.find(action.message_id);
      const tapback = target ? reaction(tapbackEmoji(action.tapback), target) : null;
      await sendOrFallBack(space, tapback, action.fallback_text, recent);
      return;
    }
    case "link":
      await sendOrFallBack(space, richlink(action.url), action.url, recent);
      return;
    case "card": {
      // Spectrum carries the card as custom content, so it still goes through
      // Photon's SDK; only the Linq platform knows how to put it on the wire.
      // Lines without an iMessage app part send the caption instead.
      const text = `${action.caption}\n${action.fallback_text}`;
      await sendOrFallBack(space, custom(action), text, recent);
      return;
    }
  }
}

// Spectrum resolves a send to nothing when the line can't do it (a tapback in
// local mode, say), so the plain-text version goes instead.
async function sendOrFallBack(
  space: Space,
  content: ContentInput | null,
  fallbackText: string,
  recent: RecentMessages,
): Promise<void> {
  const sent = content ? await space.send(content) : undefined;
  recent.remember(sent ?? (await space.send(fallbackText)));
}

class RecentMessages {
  private readonly byId = new Map<string, Message>();

  remember(message: Message | undefined): void {
    if (!message) return;
    this.byId.set(message.id, message);
    if (this.byId.size > REMEMBERED_MESSAGES) {
      const oldest = this.byId.keys().next().value;
      if (oldest !== undefined) this.byId.delete(oldest);
    }
  }

  find(id: string): Message | undefined {
    return this.byId.get(id);
  }
}

function readForScout(space: Space, message: Message): ScoutMessage | ScoutTapback | Skipped {
  if (message.direction === "outbound") return { skipReason: "scout's own message" };
  if (!message.sender) return { skipReason: "no sender" };
  if (isLocalDirectMessage(space)) {
    return { skipReason: "a private chat with scout's local account" };
  }
  const senderPhone = message.sender.id;
  if (message.content.type === "reaction") {
    const { emoji, target } = message.content;
    return { kind: "tapback", senderPhone, tapback: tapbackNamed(emoji) ?? emoji, targetId: target.id };
  }
  // Typing indicators, voice memos and the like aren't for scout.
  const parts = readableParts(message.content);
  if (!parts) return { skipReason: `nothing scout can read (${message.content.type})` };
  return { kind: "message", ...parts, senderPhone, replyToId: repliedToId(message) };
}

// Linq and the console mark a threaded reply with the ID of the message it
// answers, as Photon's terminal provider does. Declaring this as a platform's
// message schema makes Spectrum keep it on the message.
export const threadedReplySchema = z.object({
  replyTo: z.object({ messageId: z.string() }).optional(),
});

function repliedToId(message: Message): string | null {
  const { replyTo } = message as { replyTo?: { messageId?: string } };
  return replyTo?.messageId ?? null;
}

// A message by its ID, from the messages the relay remembers or else from the
// line itself. Undefined if neither has it.
async function findMessage(
  space: Space,
  messageId: string,
  recent: RecentMessages,
): Promise<Message | undefined> {
  const remembered = recent.find(messageId);
  if (remembered) return remembered;
  try {
    return await space.getMessage(messageId);
  } catch (error) {
    if (error instanceof UnsupportedError) return undefined;
    throw error;
  }
}

async function findText(space: Space, messageId: string, recent: RecentMessages): Promise<string | null> {
  const message = await findMessage(space, messageId, recent);
  return message?.content.type === "text" ? message.content.text : null;
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

// Lets scout count group members who haven't texted yet. Cloud group chats and
// the developer console can list members. Elsewhere scout learns who's in the
// group as people text, so an empty list is expected there.
async function listParticipants(space: Space, message: Message): Promise<string[]> {
  if (message.platform === "imessage" && imessage(space).type !== "group") {
    return [];
  }
  try {
    const members = await space.getMembers();
    return members.map((member) => member.id);
  } catch (error) {
    // Photon's shared-pool lines and local mode can't list group members.
    if (error instanceof UnsupportedError) return [];
    throw error;
  }
}

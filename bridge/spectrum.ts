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
import { askScout, tellScoutAboutTapback, type IncomingAttachment, type ScoutAction } from "./scout";
import { tapbackEmoji, tapbackNamed } from "./tapbacks";
import { secondsSince, type RelayReport, type Skipped } from "./trace";

type Attachment = Extract<Content, { type: "attachment" }>;

// What scout can use from one message: its words and its first photo or
// voice note.
type ReadableParts = { text: string; attachment: Attachment | null };
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

// How long scout shows it's typing before a text, from the text. Real chats
// use typingPauseFor, so a reply doesn't land the instant someone asks; tests
// and the developer console skip the wait.
export type TypingPause = (text: string) => number;

// About as long as the text: a quick "Got it" lands fast and a summary takes a
// few seconds, but no text keeps the group waiting long.
const TYPING_MS_PER_CHARACTER = 25;
const SHORTEST_TYPING_MS = 800;
const LONGEST_TYPING_MS = 5000;

export function typingPauseFor(text: string): number {
  const pause = text.length * TYPING_MS_PER_CHARACTER;
  return Math.min(LONGEST_TYPING_MS, Math.max(SHORTEST_TYPING_MS, pause));
}

export const noTypingPause: TypingPause = () => 0;

export async function relaySpectrumMessages(
  app: SpectrumInstance,
  report: RelayReport,
  typingPause: TypingPause,
): Promise<void> {
  const recent = new RecentMessages();
  const typing = new TypingIndicator(typingPause);
  // Messages are handled one at a time, on purpose: scout finishes replying to
  // one text before it reads the next, so its view of the trip is never stale.
  for await (const [space, message] of app.messages) {
    recent.remember(message);
    const startedAt = performance.now();
    const outcome = { id: message.id, chatId: space.id };
    const readable = readForScout(space, message);
    if ("skipReason" in readable) {
      report.finished({ ...outcome, kind: "skipped", reason: readable.skipReason });
      continue;
    }

    try {
      const arrival = { ...outcome, senderPhone: readable.senderPhone, at: message.timestamp };
      let actions: ScoutAction[];
      if (readable.kind === "tapback") {
        const tappedText = await findText(space, readable.targetId, recent);
        report.arrived({ ...arrival, said: describeTapback(readable.tapback, tappedText) });
        actions = await tellScoutAboutTapback({
          space_id: space.id,
          sender_phone: readable.senderPhone,
          tapback: readable.tapback,
          message_id: readable.targetId,
          message_text: tappedText,
          sent_at: message.timestamp.toISOString(),
        });
      } else {
        const repliedToText = readable.replyToId
          ? await findText(space, readable.replyToId, recent)
          : null;
        report.arrived({ ...arrival, said: describeMessage(readable, repliedToText) });
        actions = await askScout({
          space_id: space.id,
          sender_phone: readable.senderPhone,
          text: readable.text,
          sent_at: message.timestamp.toISOString(),
          participant_phones: await listParticipants(space, message),
          attachment: readable.attachment ? await asIncoming(readable.attachment) : null,
          message_id: message.id,
          reply_to_text: repliedToText,
        });
      }
      for (const action of actions) {
        await perform(space, action, { recent, typing });
      }
      report.finished({ ...outcome, kind: "handled", sent: actions, seconds: secondsSince(startedAt) });
    } catch (error) {
      // Keep listening: one failed message shouldn't take scout offline.
      report.finished({ ...outcome, kind: "failed", error });
    }
  }
}

// The file as it was sent: scout keeps the original and converts it itself.
async function asIncoming(attachment: Attachment): Promise<IncomingAttachment> {
  const bytes = await attachment.read();
  return { media_type: attachment.mimeType, base64_data: bytes.toString("base64") };
}

// How a member's message reads in the bridge's log.
function describeMessage({ text, attachment }: ReadableParts, repliedToText: string | null): string {
  const words = attachment ? `[${attachmentKind(attachment)}] ${text}`.trim() : text;
  return repliedToText === null ? words : `(replying to "${repliedToText}") ${words}`;
}

function describeTapback(tapback: string, tappedText: string | null): string {
  const emoji = tapbackEmoji(tapback as Parameters<typeof tapbackEmoji>[0]) ?? tapback;
  return tappedText === null ? `${emoji} on a message` : `${emoji} on "${tappedText}"`;
}

// What the relay keeps across messages to send scout's actions well.
type SendingState = { recent: RecentMessages; typing: TypingIndicator };

async function perform(
  space: Space,
  action: ScoutAction,
  { recent, typing }: SendingState,
): Promise<void> {
  switch (action.type) {
    case "say": {
      const thread = action.reply_to ? await findMessage(space, action.reply_to, recent) : undefined;
      await typing.typeOut(space, action.text, () =>
        sendOrFallBack(space, thread ? reply(action.text, thread) : null, action.text, recent),
      );
      return;
    }
    case "react": {
      const target = recent.find(action.message_id);
      const tapback = target ? reaction(tapbackEmoji(action.tapback), target) : null;
      await sendOrFallBack(space, tapback, action.fallback_text, recent);
      return;
    }
    case "link":
      await typing.typeOut(space, action.url, () =>
        sendOrFallBack(space, richlink(action.url), action.url, recent),
      );
      return;
    case "card": {
      // Spectrum carries the card as custom content, so it still goes through
      // Photon's SDK; only the Linq platform knows how to put it on the wire.
      // Lines without an iMessage app part send the caption instead.
      const text = `${action.caption}\n${action.fallback_text}`;
      await typing.typeOut(space, action.caption, () => sendOrFallBack(space, custom(action), text, recent));
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

// Shows the typing bubble for as long as a text would take to type, then
// sends it. Tapbacks skip the bubble, as a person's would. Lines that can't
// show the bubble skip it, and scout still pauses.
class TypingIndicator {
  constructor(private readonly pause: TypingPause) {}

  async typeOut(space: Space, text: string, send: () => Promise<void>): Promise<void> {
    const milliseconds = this.pause(text);
    if (milliseconds <= 0) return send();
    await space.startTyping();
    await Bun.sleep(milliseconds);
    // A plain text clears the bubble when it lands, but a card or link may
    // not, and a failed send never does, so scout stops it explicitly.
    try {
      await send();
    } finally {
      await space.stopTyping();
    }
  }
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
  // Typing indicators, videos and the like aren't for scout.
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
  if (content.type === "text") return { text: content.text, attachment: null };
  if (isPhotoOrVoiceNote(content)) return { text: "", attachment: content };
  if (content.type !== "group") return null;

  const items = content.items.map((item) => item.content);
  const text = items.find((item) => item.type === "text");
  const attachment = items.find(isPhotoOrVoiceNote);
  if (!text && !attachment) return null;
  return {
    text: text?.type === "text" ? text.text : "",
    attachment: attachment ?? null,
  };
}

function isPhotoOrVoiceNote(content: Content): content is Attachment {
  return content.type === "attachment" && attachmentKind(content) !== null;
}

function attachmentKind(attachment: Attachment): "photo" | "voice note" | null {
  if (attachment.mimeType.startsWith("image/")) return "photo";
  if (attachment.mimeType.startsWith("audio/")) return "voice note";
  return null;
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

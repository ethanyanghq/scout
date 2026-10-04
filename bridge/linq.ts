// Connects scout to iMessage group chats through a Linq line (linqapp.com), as
// a Spectrum platform. Linq's messages go through Photon's SDK and the bridge's
// one relay loop (spectrum.ts), like every other line.
//
// Linq runs the iMessage account, so this mode needs no Apple ID on this Mac:
// a member adds the Linq number to their group, and Linq reports every message
// as a webhook. `linq webhooks listen --forward-to` relays those webhooks to
// this machine, so scout needs no public URL.

import { UnsupportedError, definePlatform, stream, type Content, type Message } from "spectrum-ts";
import {
  asAttachment,
  asGroup,
  asReaction,
  type ProviderMessageRecord,
} from "spectrum-ts/authoring";
import z from "zod";
import { cardPart, cardProblems, type HermesCard } from "./hermes-card";
import { LINQ_API_URL, LinqApiError, callLinq, type LinqApi, type LinqHandle } from "./linq-api";
import { RivalGuard } from "./rival-guard";
import { threadedReplySchema } from "./spectrum";
import { isTapback, tapbackEmoji, tapbackNamed } from "./tapbacks";
import { consoleReport, isSkipped, type Skipped } from "./trace";

const PLATFORM = "linq";
export const WEBHOOK_PORT = 8788;
const WEBHOOK_PATH = "/linq-events";
// Where `linq webhooks listen --forward-to` sends Linq's events.
export const WEBHOOK_URL = `http://127.0.0.1:${WEBHOOK_PORT}${WEBHOOK_PATH}`;

export type LinqEvent = {
  event_type: string;
  event_id: string;
  data: unknown;
};

// The real API and webhook port unless a test stands in for them.
export type LinqConnection = { apiKey: string; apiUrl?: string; webhookPort?: number };

type LinqPart =
  | { type: "text"; value: string }
  | { type: "media"; url: string; mime_type: string };

// A reaction.added event's data.
type AddedReaction = {
  chat_id: string;
  message_id: string;
  // A tapback ("love"), "custom" for another emoji, or "sticker".
  reaction_type: string;
  custom_emoji: string | null;
  is_from_me: boolean;
  from: string;
  reacted_at: string;
};

// The parts of a message that readParts needs, from a webhook or the API.
type LinqMessageParts = { id: string; parts: LinqPart[] };

// A message.received event's data, in Linq's 2026-02-03 webhook format.
type ReceivedMessage = {
  id: string;
  chat: { id: string; is_group: boolean };
  direction: "inbound" | "outbound";
  sender_handle: LinqHandle;
  parts: LinqPart[];
  sent_at: string;
  // Set when the message is a threaded reply.
  reply_to?: { message_id: string } | null;
};

export function linqPlatform(connection: LinqConnection) {
  const api = { apiKey: connection.apiKey, apiUrl: connection.apiUrl ?? LINQ_API_URL };
  const chatsWithoutTyping = new Set<string>();
  const rivalGuard = new RivalGuard();
  return definePlatform(PLATFORM, {
    config: z.object({}),
    message: { schema: threadedReplySchema },
    user: { resolve: async ({ input }) => ({ id: input.userID }) },
    space: {
      create: async (): Promise<{ id: string }> => {
        throw UnsupportedError.action("space.create", PLATFORM, "members add scout to their groups");
      },
    },
    lifecycle: { createClient: async () => api },
    messages: () =>
      stream<ProviderMessageRecord>((emit) =>
        receiveWebhookEvents(connection.webhookPort ?? WEBHOOK_PORT, emit, rivalGuard),
      ),
    actions: {
      getMembers: async (_, space) => listMembers(api, space.id),
      getMessage: async (_, __, messageId) => fetchMessage(api, messageId),
    },
    send: async ({ space, content }) => {
      if (content.type === "typing") return setTyping(api, space.id, content.state, chatsWithoutTyping);
      await rivalGuard.assertNobodyElseAnswered(api, space.id);
      const sent = await sendContent(api, space.id, content);
      rivalGuard.noteOwnMessage(sent.id);
      return sent;
    },
  });
}

// Turns one Linq event into a message for Spectrum, or says why scout skips it.
export function readLinqEvent(event: LinqEvent): ProviderMessageRecord | Skipped {
  if (event.event_type === "reaction.added") return readTapback(event);
  if (event.event_type === "reaction.removed") {
    return { skipReason: "a removed tapback (a vote it made stays counted)" };
  }
  if (event.event_type !== "message.received") {
    return { skipReason: `not a new message (${event.event_type})` };
  }
  const message = event.data as ReceivedMessage;
  if (message.direction !== "inbound" || message.sender_handle.is_me) {
    return { skipReason: "scout's own message" };
  }
  // Linq's free line only answers people who texted it privately first, so
  // every member says hi to scout one-on-one. scout uses that chat to learn
  // their name (private_chat.py) and never starts a trip in it.
  const content = readParts(message);
  if (!content) return { skipReason: "nothing in it" };
  return {
    id: message.id,
    content,
    sender: { id: message.sender_handle.handle },
    space: { id: message.chat.id },
    timestamp: new Date(message.sent_at),
    ...(message.reply_to ? { replyTo: { messageId: message.reply_to.message_id } } : {}),
  };
}

// The target is only an ID here: Spectrum needs no more of it, and the relay
// looks up the message's words when it needs them.
function readTapback(event: LinqEvent): ProviderMessageRecord | Skipped {
  const reaction = event.data as AddedReaction;
  if (reaction.is_from_me) return { skipReason: "scout's own tapback" };
  const emoji = isTapback(reaction.reaction_type)
    ? tapbackEmoji(reaction.reaction_type)
    : reaction.custom_emoji;
  if (!emoji) return { skipReason: `a ${reaction.reaction_type} reaction` };

  const target = { id: reaction.message_id, content: { type: "text", text: "" } };
  return {
    id: event.event_id,
    content: asReaction({ emoji, target: target as unknown as Message }),
    sender: { id: reaction.from },
    space: { id: reaction.chat_id },
    timestamp: new Date(reaction.reacted_at),
  };
}

// Text parts become one text, and each media part an attachment. A photo
// sent with a caption becomes a group of the two, as in Photon's iMessage.
function readParts(message: LinqMessageParts): Content | null {
  const texts = message.parts.flatMap((part) => (part.type === "text" ? [part.value] : []));
  const media = message.parts.flatMap((part) => (part.type === "media" ? [part] : []));
  const items: Content[] = [
    ...(texts.length > 0 ? [{ type: "text" as const, text: texts.join("\n") }] : []),
    ...media.map((part) =>
      asAttachment({
        name: part.url.split("/").pop() ?? "attachment",
        mimeType: part.mime_type,
        read: () => download(part.url),
      }),
    ),
  ];
  if (items.length <= 1) return items[0] ?? null;
  // Spectrum only needs each item's id and content, not a whole Message.
  const groupItems = items.map((content, index) => ({ id: `${message.id}:${index}`, content }));
  return asGroup({ items: groupItems as unknown as Message[] });
}

// Answers each delivery right away and hands the event to Spectrum, so a slow
// reply from Claude never holds up the next delivery. The server listens on
// 127.0.0.1 only, and the CLI signs with a new secret every session, so
// deliveries aren't signature-checked.
function receiveWebhookEvents(
  port: number,
  emit: (record: ProviderMessageRecord) => Promise<void>,
  rivalGuard: RivalGuard,
): () => void {
  // Linq delivers each event at least once, so a retry can repeat one.
  const seenEventIds = new Set<string>();
  // Chained, so Spectrum gets messages in the order Linq sent them.
  let delivered = Promise.resolve();

  const server = Bun.serve({
    hostname: "127.0.0.1",
    port,
    async fetch(request) {
      if (request.method !== "POST" || new URL(request.url).pathname !== WEBHOOK_PATH) {
        return new Response("Not found", { status: 404 });
      }
      const event = (await request.json()) as LinqEvent;
      const record: ProviderMessageRecord | Skipped = seenEventIds.has(event.event_id)
        ? { skipReason: "repeat delivery" }
        : readLinqEvent(event);
      seenEventIds.add(event.event_id);
      if (isSkipped(record)) {
        if (isAboutAMemberMessage(event)) {
          consoleReport.finished({ id: event.event_id, chatId: null, kind: "skipped", reason: record.skipReason });
        }
      } else {
        if (record.space && record.timestamp) rivalGuard.noteMemberMessage(record.space.id, record.timestamp);
        delivered = delivered.then(() => emit(record));
      }
      return new Response(null, { status: 204 });
    },
  });
  return () => server.stop(true);
}

// Linq also reports scout's own sends, deliveries, read receipts and typing.
// Logging a skip for each would bury the conversation, so only skipped member
// messages and tapbacks are worth a line.
function isAboutAMemberMessage(event: LinqEvent): boolean {
  return event.event_type === "message.received" || event.event_type.startsWith("reaction.");
}

// Lets scout count group members who haven't texted yet.
async function listMembers(api: LinqApi, chatId: string): Promise<{ id: string }[]> {
  const chat = (await callLinq(api, `/chats/${chatId}`)) as { handles: LinqHandle[] };
  return chat.handles
    .filter((member) => !member.is_me && member.status === "active")
    .map((member) => ({ id: member.handle }));
}

// Lets the relay read a message it doesn't remember, such as a poll option
// someone tapped after the bridge restarted.
async function fetchMessage(
  api: LinqApi,
  messageId: string,
): Promise<ProviderMessageRecord | undefined> {
  const message = (await callLinq(api, `/messages/${messageId}`)) as LinqMessageParts & {
    chat_id: string;
    is_from_me: boolean;
    created_at: string;
  };
  const content = readParts(message);
  if (!content) return undefined;
  return {
    id: message.id,
    content,
    direction: message.is_from_me ? "outbound" : "inbound",
    space: { id: message.chat_id },
    timestamp: new Date(message.created_at),
  };
}

// Sending by chat ID keeps the reply in this exact group, from scout's number.
async function sendContent(
  api: LinqApi,
  chatId: string,
  content: Content,
): Promise<ProviderMessageRecord> {
  if (content.type === "reaction") return sendTapback(api, chatId, content);
  if (content.type === "custom") return sendCard(api, chatId, content);
  if (content.type === "richlink") return sendParts(api, chatId, content, [{ type: "link", value: content.url }]);
  const threadUnder = content.type === "reply" ? content.target.id : null;
  const words = content.type === "reply" ? content.content : content;
  if (words.type !== "text") throw UnsupportedError.content(content.type, PLATFORM);
  return sendParts(api, chatId, content, [{ type: "text", value: words.text }], threadUnder);
}

// A link part must be the only part in its message, which is why links are
// their own action.
async function sendParts(
  api: LinqApi,
  chatId: string,
  content: Content,
  parts: { type: "text" | "link"; value: string }[],
  threadUnder: string | null = null,
): Promise<ProviderMessageRecord> {
  const sent = (await callLinq(api, `/chats/${chatId}/messages`, {
    body: {
      message: {
        parts,
        ...(threadUnder ? { reply_to: { message_id: threadUnder, part_index: 0 } } : {}),
      },
    },
  })) as { message: { id: string } };
  return { id: sent.message.id, content, space: { id: chatId }, timestamp: new Date() };
}

// A card the line can't send throws UnsupportedError, so the relay sends its
// text instead.
async function sendCard(
  api: LinqApi,
  chatId: string,
  content: Extract<Content, { type: "custom" }>,
): Promise<ProviderMessageRecord> {
  const card = content.raw as HermesCard;
  const problems = cardProblems(card);
  if (problems.length > 0) throw UnsupportedError.content("custom", PLATFORM, problems.join("; "));
  const sent = (await callLinq(api, `/chats/${chatId}/messages`, {
    body: { message: { parts: [cardPart(card)] } },
  })) as { message: { id: string } };
  return { id: sent.message.id, content, space: { id: chatId }, timestamp: new Date() };
}

// Linq refuses typing indicators in group chats (403), which is where scout
// lives. After the first refusal in a chat, scout stops asking there.
async function setTyping(
  api: LinqApi,
  chatId: string,
  state: "start" | "stop",
  chatsWithoutTyping: Set<string>,
): Promise<undefined> {
  if (chatsWithoutTyping.has(chatId)) return undefined;
  try {
    await callLinq(api, `/chats/${chatId}/typing`, { method: state === "start" ? "POST" : "DELETE" });
  } catch (error) {
    if (!(error instanceof LinqApiError && error.status === 403)) throw error;
    chatsWithoutTyping.add(chatId);
    console.log(`Linq can't show scout typing in chat ${chatId}, so scout just pauses before replying.`);
  }
  return undefined;
}

async function sendTapback(
  api: LinqApi,
  chatId: string,
  content: Extract<Content, { type: "reaction" }>,
): Promise<ProviderMessageRecord> {
  const tapback = tapbackNamed(content.emoji);
  if (!tapback) throw UnsupportedError.content("reaction", PLATFORM, "scout only sends tapbacks");
  await callLinq(api, `/messages/${content.target.id}/reactions`, {
    body: { operation: "add", type: tapback },
  });
  return {
    id: `${content.target.id}:${tapback}`,
    content,
    space: { id: chatId },
    timestamp: new Date(),
  };
}

async function download(url: string): Promise<Buffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Couldn't download photo ${url}: ${response.status}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

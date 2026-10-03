// Connects scout to iMessage group chats through a Linq line (linqapp.com), as
// a Spectrum platform. Linq's messages go through Photon's SDK and the bridge's
// one relay loop (spectrum.ts), like every other line.
//
// Linq runs the iMessage account, so this mode needs no Apple ID on this Mac:
// a member adds the Linq number to their group, and Linq reports every message
// as a webhook. `linq webhooks listen --forward-to` relays those webhooks to
// this machine, so scout needs no public URL.

import { UnsupportedError, definePlatform, stream, type Content, type Message } from "spectrum-ts";
import { asAttachment, asGroup, type ProviderMessageRecord } from "spectrum-ts/authoring";
import z from "zod";
import { isSkipped, logOutcome, type Skipped } from "./trace";

const PLATFORM = "linq";
const LINQ_API_URL = "https://api.linqapp.com/api/partner/v3";
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

type LinqHandle = { handle: string; is_me: boolean; status: string };

type LinqPart =
  | { type: "text"; value: string }
  | { type: "media"; url: string; mime_type: string };

// A message.received event's data, in Linq's 2026-02-03 webhook format.
type ReceivedMessage = {
  id: string;
  chat: { id: string; is_group: boolean };
  direction: "inbound" | "outbound";
  sender_handle: LinqHandle;
  parts: LinqPart[];
  sent_at: string;
};

export function linqPlatform(connection: LinqConnection) {
  const api = { apiKey: connection.apiKey, apiUrl: connection.apiUrl ?? LINQ_API_URL };
  return definePlatform(PLATFORM, {
    config: z.object({}),
    user: { resolve: async ({ input }) => ({ id: input.userID }) },
    space: {
      create: async (): Promise<{ id: string }> => {
        throw UnsupportedError.action("space.create", PLATFORM, "members add scout to their groups");
      },
    },
    lifecycle: { createClient: async () => api },
    messages: () =>
      stream<ProviderMessageRecord>((emit) =>
        receiveWebhookEvents(connection.webhookPort ?? WEBHOOK_PORT, emit),
      ),
    actions: { getMembers: async (_, space) => listMembers(api, space.id) },
    send: async ({ space, content }) => sendContent(api, space.id, content),
  });
}

// Turns one Linq event into a message for Spectrum, or says why scout skips it.
export function readLinqEvent(event: LinqEvent): ProviderMessageRecord | Skipped {
  if (event.event_type !== "message.received") {
    return { skipReason: `not a new message (${event.event_type})` };
  }
  const message = event.data as ReceivedMessage;
  if (message.direction !== "inbound" || message.sender_handle.is_me) {
    return { skipReason: "scout's own message" };
  }
  // Linq's free line only answers people who texted it privately first, so
  // every member says hi to scout one-on-one. Those hellos mustn't start trips.
  if (!message.chat.is_group) return { skipReason: "a private chat, not a group" };

  const content = readParts(message);
  if (!content) return { skipReason: "nothing in it" };
  return {
    id: message.id,
    content,
    sender: { id: message.sender_handle.handle },
    space: { id: message.chat.id },
    timestamp: new Date(message.sent_at),
  };
}

// Text parts become one text, and each media part an attachment. A photo
// sent with a caption becomes a group of the two, as in Photon's iMessage.
function readParts(message: ReceivedMessage): Content | null {
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
        logOutcome({ id: event.event_id, chatId: null, kind: "skipped", reason: record.skipReason });
      } else {
        delivered = delivered.then(() => emit(record));
      }
      return new Response(null, { status: 204 });
    },
  });
  return () => server.stop(true);
}

type LinqApi = { apiKey: string; apiUrl: string };

// Lets scout count group members who haven't texted yet.
async function listMembers(api: LinqApi, chatId: string): Promise<{ id: string }[]> {
  const chat = (await callLinq(api, `/chats/${chatId}`)) as { handles: LinqHandle[] };
  return chat.handles
    .filter((member) => !member.is_me && member.status === "active")
    .map((member) => ({ id: member.handle }));
}

// Sending by chat ID keeps the reply in this exact group, from scout's number.
async function sendContent(
  api: LinqApi,
  chatId: string,
  content: Content,
): Promise<ProviderMessageRecord> {
  if (content.type !== "text") throw UnsupportedError.content(content.type, PLATFORM);
  const sent = (await callLinq(api, `/chats/${chatId}/messages`, {
    message: { parts: [{ type: "text", value: content.text }] },
  })) as { message: { id: string } };
  return { id: sent.message.id, content, space: { id: chatId }, timestamp: new Date() };
}

async function callLinq(api: LinqApi, path: string, body?: object): Promise<unknown> {
  const response = await fetch(`${api.apiUrl}${path}`, {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${api.apiKey}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new Error(`Linq ${path} returned ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function download(url: string): Promise<Buffer> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Couldn't download photo ${url}: ${response.status}`);
  }
  return Buffer.from(await response.arrayBuffer());
}

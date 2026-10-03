// Connects scout to iMessage group chats through a Linq line (linqapp.com).
//
// Linq runs the iMessage account, so this mode needs no Apple ID on this Mac:
// a member adds the Linq number to their group, and Linq reports every message
// as a webhook. `linq webhooks listen --forward-to` relays those webhooks to
// this machine, so scout needs no public URL.

import { askScout, toJpeg } from "./scout";
import { logOutcome, secondsSince, type Skipped } from "./trace";

const LINQ_API_URL = "https://api.linqapp.com/api/partner/v3";
const WEBHOOK_PORT = 8788;
const WEBHOOK_PATH = "/linq-events";

export type LinqEvent = {
  event_type: string;
  event_id: string;
  data: unknown;
};

type LinqHandle = { handle: string; is_me: boolean; status: string };

type LinqPart =
  | { type: "text"; value: string }
  | { type: "media"; url: string; mime_type: string };

type ReceivedMessage = {
  chat: { id: string; is_group: boolean };
  direction: "inbound" | "outbound";
  sender_handle: LinqHandle;
  parts: LinqPart[];
  sent_at: string;
};

// What scout can use from one group message.
export type GroupMessage = {
  chatId: string;
  senderPhone: string;
  text: string;
  sentAt: string;
  photoUrl: string | null;
};

export async function relayLinqGroupMessages(apiKey: string): Promise<void> {
  const events = receiveWebhookEvents();
  const forwardTo = `http://127.0.0.1:${WEBHOOK_PORT}${WEBHOOK_PATH}`;
  console.log(`scout bridge is waiting for Linq events. In another terminal, run:`);
  console.log(`  linq webhooks listen --forward-to ${forwardTo}`);

  // Linq delivers each event at least once, so a retry can repeat one.
  const handledEventIds = new Set<string>();
  // Messages are handled one at a time, on purpose: scout finishes replying to
  // one text before it reads the next, so its view of the trip is never stale.
  for await (const event of events) {
    const startedAt = performance.now();
    if (handledEventIds.has(event.event_id)) {
      logOutcome({ id: event.event_id, chatId: null, kind: "skipped", reason: "repeat delivery" });
      continue;
    }
    handledEventIds.add(event.event_id);
    const message = readGroupMessage(event);
    if ("skipReason" in message) {
      logOutcome({ id: event.event_id, chatId: null, kind: "skipped", reason: message.skipReason });
      continue;
    }

    const outcome = { id: event.event_id, chatId: message.chatId };
    try {
      const replies = await askScout({
        space_id: message.chatId,
        sender_phone: message.senderPhone,
        text: message.text,
        sent_at: message.sentAt,
        participant_phones: await listMemberPhones(apiKey, message.chatId),
        photo: message.photoUrl ? await toJpeg(await download(message.photoUrl)) : null,
      });
      for (const reply of replies) {
        await sendText(apiKey, message.chatId, reply);
      }
      logOutcome({
        ...outcome,
        kind: "handled",
        replyCount: replies.length,
        seconds: secondsSince(startedAt),
      });
    } catch (error) {
      // Keep listening: one failed message shouldn't take scout offline.
      logOutcome({ ...outcome, kind: "failed", error });
    }
  }
}

export function readGroupMessage(event: LinqEvent): GroupMessage | Skipped {
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

  const text = message.parts
    .flatMap((part) => (part.type === "text" ? [part.value] : []))
    .join("\n");
  const photo = message.parts.find(
    (part) => part.type === "media" && part.mime_type.startsWith("image/"),
  );
  // Stickers, voice memos and the like aren't for scout.
  if (!text && !photo) return { skipReason: "nothing scout can read (no text or photo)" };

  return {
    chatId: message.chat.id,
    senderPhone: message.sender_handle.handle,
    text,
    sentAt: message.sent_at,
    photoUrl: photo?.type === "media" ? photo.url : null,
  };
}

// Answers each delivery right away and queues the event, so a slow reply from
// Claude never holds up the next delivery. The server listens on 127.0.0.1
// only, and the CLI signs with a new secret every session, so deliveries
// aren't signature-checked.
function receiveWebhookEvents(): ReadableStream<LinqEvent> {
  return new ReadableStream<LinqEvent>({
    start(queue) {
      Bun.serve({
        hostname: "127.0.0.1",
        port: WEBHOOK_PORT,
        async fetch(request) {
          if (request.method !== "POST" || new URL(request.url).pathname !== WEBHOOK_PATH) {
            return new Response("Not found", { status: 404 });
          }
          queue.enqueue((await request.json()) as LinqEvent);
          return new Response(null, { status: 204 });
        },
      });
    },
  });
}

// Lets scout count group members who haven't texted yet.
async function listMemberPhones(apiKey: string, chatId: string): Promise<string[]> {
  const chat = (await callLinq(apiKey, `/chats/${chatId}`)) as { handles: LinqHandle[] };
  return chat.handles
    .filter((member) => !member.is_me && member.status === "active")
    .map((member) => member.handle);
}

// Sending by chat ID keeps the reply in this exact group, from scout's number.
async function sendText(apiKey: string, chatId: string, text: string): Promise<void> {
  await callLinq(apiKey, `/chats/${chatId}/messages`, {
    message: { parts: [{ type: "text", value: text }] },
  });
}

async function callLinq(apiKey: string, path: string, body?: object): Promise<unknown> {
  const response = await fetch(`${LINQ_API_URL}${path}`, {
    method: body ? "POST" : "GET",
    headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
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

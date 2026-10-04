import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { Spectrum } from "spectrum-ts";
import { linqPlatform, readLinqEvent, type LinqEvent } from "./linq";
import { AnotherScoutAnsweredError } from "./rival-guard";
import type { IncomingText } from "./scout";
import { noTypingPause, relaySpectrumMessages, type TypingPause } from "./spectrum";
import type { MessageOutcome } from "./trace";

const SCOUT = { handle: "+12055550100", is_me: true, status: "active" };
const MAYA = { handle: "+16075550123", is_me: false, status: "active" };
const LEO = { handle: "+16075550124", is_me: false, status: "active" };

function messageReceived(overrides: {
  isGroup?: boolean;
  sender?: typeof MAYA;
  direction?: string;
  parts?: object[];
}): LinqEvent {
  return {
    event_type: "message.received",
    event_id: "event-1",
    data: {
      id: "message-1",
      chat: { id: "group-chat-1", is_group: overrides.isGroup ?? true },
      direction: overrides.direction ?? "inbound",
      sender_handle: overrides.sender ?? MAYA,
      parts: overrides.parts ?? [{ type: "text", value: "@scout spring break?" }],
      sent_at: "2026-10-03T20:37:25.714Z",
    },
  };
}

const RECEIPT = { type: "media", url: "https://cdn.example/receipt.jpeg", mime_type: "image/jpeg" };
const SAN_JUAN_OPTION = "2. San Juan, Puerto Rico (~$750/person est.): No passport";

function reactionAdded(overrides: { type?: string; isFromMe?: boolean } = {}): LinqEvent {
  return {
    event_type: "reaction.added",
    event_id: "event-2",
    data: {
      chat_id: "group-chat-1",
      message_id: "poll-option-2",
      part_index: 0,
      reaction_type: overrides.type ?? "like",
      custom_emoji: null,
      is_from_me: overrides.isFromMe ?? false,
      from: LEO.handle,
      reacted_at: "2026-10-03T20:40:00.000Z",
    },
  };
}

describe("reading a Linq event", () => {
  test("reads the id, chat, sender, text and time of a group text", () => {
    expect(readLinqEvent(messageReceived({}))).toEqual({
      id: "message-1",
      content: { type: "text", text: "@scout spring break?" },
      sender: { id: MAYA.handle },
      space: { id: "group-chat-1" },
      timestamp: new Date("2026-10-03T20:37:25.714Z"),
    });
  });

  test("keeps a photo's caption alongside the photo", () => {
    const record = readLinqEvent(
      messageReceived({ parts: [{ type: "text", value: "paid the airbnb" }, RECEIPT] }),
    );

    expect(record).toMatchObject({
      content: {
        type: "group",
        items: [
          { content: { type: "text", text: "paid the airbnb" } },
          { content: { type: "attachment", mimeType: "image/jpeg" } },
        ],
      },
    });
  });

  test("marks a threaded reply with the message it answers", () => {
    const event = messageReceived({});
    const threaded = { ...event, data: { ...(event.data as object), reply_to: { message_id: "poll-option-2" } } };

    expect(readLinqEvent(threaded)).toMatchObject({ replyTo: { messageId: "poll-option-2" } });
  });

  test("passes on private chats with scout, where it learns names", () => {
    expect(readLinqEvent(messageReceived({ isGroup: false }))).toMatchObject({
      sender: { id: MAYA.handle },
    });
  });

  test("skips scout's own messages", () => {
    const ownMessage = { skipReason: "scout's own message" };
    expect(readLinqEvent(messageReceived({ sender: SCOUT }))).toEqual(ownMessage);
    expect(readLinqEvent(messageReceived({ direction: "outbound" }))).toEqual(ownMessage);
  });

  test("reads a tapback as a reaction on the message it was added to", () => {
    expect(readLinqEvent(reactionAdded())).toMatchObject({
      id: "event-2",
      content: { type: "reaction", emoji: "👍", target: { id: "poll-option-2" } },
      sender: { id: LEO.handle },
      space: { id: "group-chat-1" },
    });
  });
});

// Linq's API and the scout service are the outside boundaries here, so stubs
// stand in for both. Spectrum and the bridge's relay loop are real.
describe("a Linq group chat through Spectrum", () => {
  let scoutReceived: IncomingText[] = [];
  let linqReceived: { path: string; body?: unknown; method?: string }[] = [];
  let scoutActions: object[] = [];
  // Linq answers 403 to typing in a group chat, so tests choose its answer.
  let typingStatus = 204;
  let sendStatus = 200;
  // What Linq lists as the chat's newest messages: another bridge's reply, say.
  let chatMessages: object[] = [];
  let scoutThinkingMs = 0;
  const stubScout = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      scoutReceived.push((await request.json()) as IncomingText);
      await Bun.sleep(scoutThinkingMs);
      return Response.json({ actions: scoutActions });
    },
  });
  const stubLinq = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (path === "/messages/poll-option-2") {
        return Response.json({
          id: "poll-option-2",
          chat_id: "group-chat-1",
          is_from_me: true,
          created_at: "2026-10-03T20:30:00.000Z",
          parts: [{ type: "text", value: SAN_JUAN_OPTION }],
        });
      }
      if (request.method === "GET" && path === "/chats/group-chat-1/messages") {
        return Response.json({ messages: chatMessages });
      }
      if (request.method === "GET") return Response.json({ handles: [SCOUT, MAYA, LEO] });
      if (path.endsWith("/typing")) {
        linqReceived.push({ path, method: request.method });
        return new Response(null, { status: typingStatus });
      }
      linqReceived.push({ path, body: await request.json() });
      if (sendStatus !== 200) return new Response(null, { status: sendStatus });
      return Response.json({ chat_id: "group-chat-1", message: { id: "sent-1" } });
    },
  });
  let realScoutUrl: string | undefined;
  beforeAll(() => {
    realScoutUrl = process.env.SCOUT_URL;
    process.env.SCOUT_URL = `http://127.0.0.1:${stubScout.port}`;
  });
  afterAll(() => {
    process.env.SCOUT_URL = realScoutUrl;
    stubScout.stop(true);
    stubLinq.stop(true);
  });

  beforeEach(() => {
    scoutReceived = [];
    linqReceived = [];
    typingStatus = 204;
    sendStatus = 200;
    chatMessages = [];
    scoutThinkingMs = 0;
  });

  // Sends one Linq event through Spectrum and the relay, and waits until scout
  // has finished with it.
  async function deliver(
    event: LinqEvent,
    typingPause: TypingPause = noTypingPause,
    showTypingAfterMs?: number,
  ): Promise<MessageOutcome> {
    const webhookPort = findFreePort();
    const platform = linqPlatform({
      apiKey: "test-key",
      apiUrl: `http://127.0.0.1:${stubLinq.port}`,
      webhookPort,
    });
    const app = await Spectrum({ providers: [platform.config({})] });
    const finished = new Promise<MessageOutcome>((resolve) => {
      // The relay stops itself when another bridge answered, which a test reads from the outcome.
      relaySpectrumMessages(app, { arrived: () => {}, finished: resolve }, typingPause, showTypingAfterMs).catch(() => {});
    });
    await fetch(`http://127.0.0.1:${webhookPort}/linq-events`, {
      method: "POST",
      body: JSON.stringify(event),
    });
    const outcome = await finished;
    await app.stop();
    return outcome;
  }

  test("hands a group text to scout with the group's members, and sends the reply to that group", async () => {
    scoutActions = [{ type: "say", text: "hey Maya 👋" }];

    const outcome = await deliver(messageReceived({}));

    expect(outcome).toMatchObject({ id: "message-1", chatId: "group-chat-1", kind: "handled" });
    expect(scoutReceived[0]).toMatchObject({
      space_id: "group-chat-1",
      sender_phone: MAYA.handle,
      text: "@scout spring break?",
      participant_phones: [MAYA.handle, LEO.handle],
      message_id: "message-1",
    });
    expect(linqReceived).toEqual([
      {
        path: "/chats/group-chat-1/messages",
        body: { message: { parts: [{ type: "text", value: "hey Maya 👋" }] } },
      },
    ]);
  });

  test("stops this bridge when another bridge on the same line already answered", async () => {
    scoutActions = [{ type: "say", text: "hey Maya 👋" }];
    chatMessages = [{ id: "rival-reply", is_from_me: true, created_at: "2026-10-03T20:37:30.000Z" }];

    const outcome = await deliver(messageReceived({}));

    expect(outcome).toMatchObject({ kind: "failed", error: expect.any(AnotherScoutAnsweredError) });
    expect(linqReceived).toEqual([]);
  });

  test("still answers when scout's last message came before the member spoke", async () => {
    scoutActions = [{ type: "say", text: "hey Maya 👋" }];
    chatMessages = [{ id: "earlier-reply", is_from_me: true, created_at: "2026-10-03T20:30:00.000Z" }];

    const outcome = await deliver(messageReceived({}));

    expect(outcome).toMatchObject({ kind: "handled" });
    expect(linqReceived).toHaveLength(1);
  });

  test("doesn't pause to type when scout already took longer than the pause to answer", async () => {
    scoutActions = [{ type: "say", text: "hey Maya 👋" }];
    scoutThinkingMs = 150;

    await deliver(messageReceived({}), () => 100);

    expect(linqReceived.map(({ path }) => path)).toEqual(["/chats/group-chat-1/messages"]);
  });

  test("shows scout typing while it works out a slow answer, and clears it before a tapback", async () => {
    scoutActions = [{ type: "react", message_id: "message-1", tapback: "like", fallback_text: "Got it" }];
    scoutThinkingMs = 150;

    await deliver(messageReceived({}), () => 1, 50);

    expect(linqReceived.map(({ path, method }) => method ?? path)).toEqual([
      "POST",
      "DELETE",
      "/messages/message-1/reactions",
    ]);
  });

  test("shows no typing for an answer that comes quickly", async () => {
    scoutActions = [{ type: "react", message_id: "message-1", tapback: "like", fallback_text: "Got it" }];

    await deliver(messageReceived({}), () => 1, 1000);

    expect(linqReceived.map(({ path }) => path)).toEqual(["/messages/message-1/reactions"]);
  });

  test("sends scout's link to Linq as a link part, so iMessage shows a card", async () => {
    scoutActions = [{ type: "link", url: "https://calendar.google.com/calendar/render?x=1" }];

    await deliver(messageReceived({}));

    expect(linqReceived).toEqual([
      {
        path: "/chats/group-chat-1/messages",
        body: {
          message: { parts: [{ type: "link", value: "https://calendar.google.com/calendar/render?x=1" }] },
        },
      },
    ]);
  });

  test("sends scout's card to Linq as a HermesShare part carrying its layout", async () => {
    const layout = { version: 1, title: "Where should we go?" };
    scoutActions = [{ type: "card", ...BROCHURE_CARD, layout }];

    await deliver(messageReceived({}));

    const [part] = (linqReceived[0]!.body as { message: { parts: Record<string, unknown>[] } }).message.parts;
    expect(part).toMatchObject({
      type: "imessage_app",
      app: { name: "HermesShare" },
      fallback_text: "Tulum · ~$1,100",
      interactive: false,
      layout: { caption: "Tulum", image_url: "https://lh3.googleusercontent.com/tulum" },
    });
    const encoded = (part!.url as string).replace("data:application/json;base64,", "");
    expect(JSON.parse(Buffer.from(encoded, "base64").toString())).toEqual(layout);
  });

  test("stops scout's typing bubble once a card is sent, since a card doesn't clear it", async () => {
    scoutActions = [{ type: "card", ...BROCHURE_CARD }];

    await deliver(messageReceived({}), () => 1);

    expect(linqReceived.map(({ path, method }) => method ?? path)).toEqual([
      "POST",
      "/chats/group-chat-1/messages",
      "DELETE",
    ]);
  });

  test("stops scout's typing bubble when Linq fails to send the reply", async () => {
    scoutActions = [{ type: "say", text: "hey Maya 👋" }];
    sendStatus = 500;

    const outcome = await deliver(messageReceived({}), () => 1);

    expect(outcome.kind).toBe("failed");
    expect(linqReceived.at(-1)).toEqual({ path: "/chats/group-chat-1/typing", method: "DELETE" });
  });

  test("sends scout's tapback to Linq on the member's message", async () => {
    scoutActions = [{ type: "react", message_id: "message-1", tapback: "like", fallback_text: "Got it" }];

    await deliver(messageReceived({ parts: [{ type: "text", value: "2" }] }));

    expect(linqReceived).toEqual([
      { path: "/messages/message-1/reactions", body: { operation: "add", type: "like" } },
    ]);
  });
});

const BROCHURE_CARD = {
  layout: {},
  caption: "Tulum",
  thumbnail_url: "https://lh3.googleusercontent.com/tulum",
  fallback_text: "Tulum · ~$1,100",
};

function findFreePort(): number {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response() });
  const port = probe.port!;
  probe.stop(true);
  return port;
}

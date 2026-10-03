import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { Spectrum } from "spectrum-ts";
import { linqPlatform, readLinqEvent, type LinqEvent } from "./linq";
import type { IncomingText } from "./scout";
import { relaySpectrumMessages } from "./spectrum";
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

  test("joins a message's text parts", () => {
    const parts = [
      { type: "text", value: "paid the airbnb" },
      { type: "text", value: "$1,240" },
    ];

    expect(readLinqEvent(messageReceived({ parts }))).toMatchObject({
      content: { type: "text", text: "paid the airbnb\n$1,240" },
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

  test("reads a photo sent without a caption", () => {
    expect(readLinqEvent(messageReceived({ parts: [RECEIPT] }))).toMatchObject({
      content: { type: "attachment", name: "receipt.jpeg", mimeType: "image/jpeg" },
    });
  });

  test("skips private chats with scout", () => {
    expect(readLinqEvent(messageReceived({ isGroup: false }))).toEqual({
      skipReason: "a private chat, not a group",
    });
  });

  test("skips scout's own messages", () => {
    const ownMessage = { skipReason: "scout's own message" };
    expect(readLinqEvent(messageReceived({ sender: SCOUT }))).toEqual(ownMessage);
    expect(readLinqEvent(messageReceived({ direction: "outbound" }))).toEqual(ownMessage);
  });

  test("skips events that aren't new messages", () => {
    const typing = { ...messageReceived({}), event_type: "chat.typing_indicator.started" };

    expect(readLinqEvent(typing)).toEqual({
      skipReason: "not a new message (chat.typing_indicator.started)",
    });
  });
});

// Linq's API and the scout service are the outside boundaries here, so stubs
// stand in for both. Spectrum and the bridge's relay loop are real.
describe("a Linq group chat through Spectrum", () => {
  let scoutReceived: IncomingText[] = [];
  let linqReceived: { path: string; body: unknown }[] = [];
  let scoutActions: object[] = [];
  const stubScout = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      scoutReceived.push((await request.json()) as IncomingText);
      return Response.json({ actions: scoutActions });
    },
  });
  const stubLinq = Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (request.method === "GET") return Response.json({ handles: [SCOUT, MAYA, LEO] });
      linqReceived.push({ path, body: await request.json() });
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
  });

  // Sends one Linq event through Spectrum and the relay, and waits until scout
  // has finished with it.
  async function deliver(event: LinqEvent): Promise<MessageOutcome> {
    const webhookPort = findFreePort();
    const platform = linqPlatform({
      apiKey: "test-key",
      apiUrl: `http://127.0.0.1:${stubLinq.port}`,
      webhookPort,
    });
    const app = await Spectrum({ providers: [platform.config({})] });
    const finished = new Promise<MessageOutcome>((resolve) => {
      relaySpectrumMessages(app, resolve);
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

  test("sends scout's tapback to Linq on the member's message", async () => {
    scoutActions = [{ type: "react", message_id: "message-1", tapback: "like", fallback_text: "Got it" }];

    await deliver(messageReceived({ parts: [{ type: "text", value: "2" }] }));

    expect(linqReceived).toEqual([
      { path: "/messages/message-1/reactions", body: { operation: "add", type: "like" } },
    ]);
  });
});

function findFreePort(): number {
  const probe = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: () => new Response() });
  const port = probe.port!;
  probe.stop(true);
  return port;
}

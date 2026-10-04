import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import type { IncomingText } from "../scout";
import { DevChat, connectDevChat, type ChatEntry, type ChatMember } from "./platform";

// The scout service is the bridge's outside boundary, so a stub stands in for
// it here. The end-to-end scripts run the console against the real service.
const staysQuiet = () => Response.json({ actions: [] });
const scoutSays = (...texts: string[]) =>
  Response.json({ actions: texts.map((text) => ({ type: "say", text })) });
let received: IncomingText[] = [];
let receivedPaths: string[] = [];
let respond: () => Response = staysQuiet;
const stubScout = Bun.serve({
  hostname: "127.0.0.1",
  port: 0,
  async fetch(request) {
    received.push((await request.json()) as IncomingText);
    receivedPaths.push(new URL(request.url).pathname);
    return respond();
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
});

const MAYA = { name: "maya", phone: "+15550000001" };
const LEO = { name: "leo", phone: "+15550000002" };
const PRIYA = { name: "priya", phone: "+15550000003" };

beforeEach(() => {
  received = [];
  receivedPaths = [];
  respond = staysQuiet;
});

async function inChat<T>(
  members: ChatMember[],
  play: (chat: DevChat) => Promise<T>,
  transcript: ChatEntry[] = [],
): Promise<T> {
  const chat = new DevChat("chat-1", members, transcript);
  const stop = await connectDevChat(chat);
  try {
    return await play(chat);
  } finally {
    await stop();
  }
}

describe("the developer console's group chat", () => {
  test("sends a member's message to scout with everyone in the group", async () => {
    await inChat([MAYA, LEO, PRIYA], (chat) => chat.say("maya", "hey @scout"));

    expect(received).toHaveLength(1);
    expect(received[0]).toMatchObject({
      space_id: "chat-1",
      sender_phone: MAYA.phone,
      text: "hey @scout",
      participant_phones: [MAYA.phone, LEO.phone, PRIYA.phone],
      attachment: null,
      message_id: "m1",
    });
  });

  test("sends a voice note to scout exactly as it was recorded", async () => {
    const memo = { fileName: "boston.caf", mimeType: "audio/x-caf", bytes: Buffer.from("opus") };

    const exchange = await inChat([MAYA, LEO], (chat) => chat.sendMediaFile("maya", memo));

    expect(exchange.sent.text).toBe("[voice note] boston.caf");
    expect(received[0]).toMatchObject({
      text: "",
      attachment: { media_type: "audio/x-caf", base64_data: Buffer.from("opus").toString("base64") },
    });
  });

  test("returns scout's replies in order, numbered after the message", async () => {
    respond = () => scoutSays("hi all", "who's in?");

    const exchange = await inChat([MAYA, LEO], (chat) => chat.say("Maya", "hey @scout"));

    expect(exchange.sent).toEqual({ id: "m1", from: "maya", text: "hey @scout" });
    expect(exchange.replies).toEqual([
      { id: "m2", from: "scout", text: "hi all" },
      { id: "m3", from: "scout", text: "who's in?" },
    ]);
    expect(exchange.outcome.kind).toBe("handled");
  });

  test("reports a failure when scout returns an error", async () => {
    respond = () => new Response("database is locked", { status: 500 });

    const exchange = await inChat([MAYA, LEO], (chat) => chat.say("maya", "2"));

    expect(exchange.outcome.kind).toBe("failed");
    expect(exchange.replies).toEqual([]);
  });

  test("handles each message before the next, in the order they were sent", async () => {
    let replyNumber = 0;
    respond = () => scoutSays(`reply ${++replyNumber}`);

    const transcript = await inChat([MAYA, LEO], async (chat) => {
      await chat.say("maya", "1");
      await chat.say("leo", "2");
      return chat.transcript;
    });

    expect(transcript.map((entry) => `${entry.from}: ${entry.text}`)).toEqual([
      "maya: 1",
      "scout: reply 1",
      "leo: 2",
      "scout: reply 2",
    ]);
  });

  test("sends a member's tapback to scout with the words of the message it's on", async () => {
    const poll = [
      { id: "m1", from: "scout", text: "🗳️ Where should we go?" },
      { id: "m2", from: "scout", text: "1. Tulum, Mexico (~$900/person est.): Beaches" },
      { id: "m3", from: "scout", text: "2. San Juan, Puerto Rico (~$750/person est.): No passport" },
    ];

    const exchange = await inChat(
      [MAYA, LEO],
      (chat) => chat.react("leo", "San Juan", "like"),
      poll,
    );

    expect(exchange.sent).toEqual({ id: "m4", from: "leo", text: "👍 on m3", tapback: "like", on: "m3" });
    expect(receivedPaths).toEqual(["/reactions"]);
    expect(received[0]).toMatchObject({
      space_id: "chat-1",
      sender_phone: LEO.phone,
      tapback: "like",
      message_text: "2. San Juan, Puerto Rico (~$750/person est.): No passport",
    });
  });

  test("sends a member's threaded reply to scout with the words it answers", async () => {
    const poll = [{ id: "m1", from: "scout", text: "2. San Juan, Puerto Rico (~$750/person est.)" }];

    const exchange = await inChat(
      [MAYA],
      (chat) => chat.reply("maya", "2. San Juan", "this one!"),
      poll,
    );

    expect(exchange.sent).toEqual({ id: "m2", from: "maya", text: "this one!", replyTo: "m1" });
    expect(received[0]).toMatchObject({
      text: "this one!",
      reply_to_text: "2. San Juan, Puerto Rico (~$750/person est.)",
    });
  });
});

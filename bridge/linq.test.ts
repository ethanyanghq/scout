import { describe, expect, test } from "bun:test";
import { readGroupMessage, type LinqEvent } from "./linq";

const SCOUT = { handle: "+12055550100", is_me: true, status: "active" };
const MAYA = { handle: "+16075550123", is_me: false, status: "active" };

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
      chat: { id: "group-chat-1", is_group: overrides.isGroup ?? true },
      direction: overrides.direction ?? "inbound",
      sender_handle: overrides.sender ?? MAYA,
      parts: overrides.parts ?? [{ type: "text", value: "@scout spring break?" }],
      sent_at: "2026-10-03T20:37:25.714Z",
    },
  };
}

describe("reading a Linq event as a group message", () => {
  test("reads the chat, sender, text and time of a group text", () => {
    expect(readGroupMessage(messageReceived({}))).toEqual({
      chatId: "group-chat-1",
      senderPhone: MAYA.handle,
      text: "@scout spring break?",
      sentAt: "2026-10-03T20:37:25.714Z",
      photoUrl: null,
    });
  });

  test("keeps a photo's caption alongside the photo", () => {
    const message = readGroupMessage(
      messageReceived({
        parts: [
          { type: "text", value: "paid the airbnb" },
          { type: "media", url: "https://cdn.example/receipt.jpeg", mime_type: "image/jpeg" },
        ],
      }),
    );
    expect(message).toMatchObject({
      text: "paid the airbnb",
      photoUrl: "https://cdn.example/receipt.jpeg",
    });
  });

  test("reads a photo sent without a caption", () => {
    const message = readGroupMessage(
      messageReceived({
        parts: [{ type: "media", url: "https://cdn.example/receipt.jpeg", mime_type: "image/jpeg" }],
      }),
    );
    expect(message).toMatchObject({ text: "", photoUrl: "https://cdn.example/receipt.jpeg" });
  });

  test("ignores private chats with scout", () => {
    expect(readGroupMessage(messageReceived({ isGroup: false }))).toEqual({
      skipReason: "a private chat, not a group",
    });
  });

  test("ignores scout's own messages", () => {
    const ownMessage = { skipReason: "scout's own message" };
    expect(readGroupMessage(messageReceived({ sender: SCOUT }))).toEqual(ownMessage);
    expect(readGroupMessage(messageReceived({ direction: "outbound" }))).toEqual(ownMessage);
  });

  test("ignores events that aren't new messages", () => {
    const typing = { ...messageReceived({}), event_type: "chat.typing_indicator.started" };
    expect(readGroupMessage(typing)).toEqual({
      skipReason: "not a new message (chat.typing_indicator.started)",
    });
  });

  test("ignores messages with nothing scout can read", () => {
    const voiceMemo = messageReceived({
      parts: [{ type: "media", url: "https://cdn.example/memo.caf", mime_type: "audio/x-caf" }],
    });
    expect(readGroupMessage(voiceMemo)).toEqual({
      skipReason: "nothing scout can read (no text or photo)",
    });
  });
});

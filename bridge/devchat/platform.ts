// The developer console's group chat: a Spectrum platform that plays a whole
// group from the terminal. Messages go through the bridge's real relay loop
// (spectrum.ts) to the real scout service. Only the iMessage line is fake.

import { basename, extname, join } from "node:path";
import { Spectrum, definePlatform, stream, type Content, type Message } from "spectrum-ts";
import {
  asAttachment,
  asReaction,
  setLogLevel,
  type ProviderMessageRecord,
} from "spectrum-ts/authoring";
import z from "zod";
import { noTypingPause, relaySpectrumMessages, threadedReplySchema } from "../spectrum";
import { tapbackEmoji, tapbackNamed, type Tapback } from "../tapbacks";
import { cardProblems, type HermesCard } from "../hermes-card";
import { previewLinkCard, type LinkCard } from "./link-card";
import type { MessageOutcome } from "../trace";

export type ChatMember = { name: string; phone: string };

// One line of the chat. `from` is a member's name, or "scout". A tapback also
// names which one it was and the message it's on, a threaded reply the
// message it's under, and a link the card iMessage would show for it.
export type ChatEntry = {
  id: string;
  from: string;
  text: string;
  tapback?: string;
  on?: string;
  replyTo?: string;
  card?: LinkCard;
};

// Where the console saves link cards' pictures, inside the git-ignored
// bridge/.devchat.
const CARDS_FOLDER = join(import.meta.dir, "..", ".devchat", "cards");

// What happened to one member's message: the bridge's outcome, and scout's
// replies to it.
export type Exchange = { sent: ChatEntry; outcome: MessageOutcome; replies: ChatEntry[] };

// A photo or voice note a member sends from a file.
export type MediaFile = { fileName: string; mimeType: string; bytes: Buffer };

// Bun doesn't know iPhone photos' and voice memos' types from the file name.
const IPHONE_MEDIA_TYPES: Record<string, string> = { ".heic": "image/heic", ".caf": "audio/x-caf" };

type InboundRecord = {
  id: string;
  content: Content;
  sender: { id: string };
  space: { id: string };
  timestamp: Date;
  replyTo?: { messageId: string };
};

type Deliver = (record: InboundRecord) => Promise<void>;

export class DevChat {
  private readonly connection = Promise.withResolvers<Deliver>();
  private readonly waitingFor = new Map<string, (outcome: MessageOutcome) => void>();

  constructor(
    readonly chatId: string,
    readonly members: ChatMember[],
    // Earlier messages, when a saved chat is reopened.
    readonly transcript: ChatEntry[] = [],
  ) {}

  say(memberName: string, text: string): Promise<Exchange> {
    return this.send(memberName, { text }, { type: "text", text });
  }

  // `target` is a message ID ("m3"), "scout.last", or words from one of
  // scout's messages, which picks the latest message of scout's that has them.
  react(memberName: string, target: string, tapback: Tapback): Promise<Exchange> {
    const on = this.findEntry(target);
    const emoji = tapbackEmoji(tapback);
    const content = asReaction({ emoji, target: asMessageStub(on) });
    return this.send(memberName, { text: `${emoji} on ${on.id}`, tapback, on: on.id }, content);
  }

  sendMediaFile(memberName: string, file: MediaFile): Promise<Exchange> {
    const content = asAttachment({
      name: file.fileName,
      mimeType: file.mimeType,
      read: async () => file.bytes,
    });
    const kind = file.mimeType.startsWith("audio/") ? "voice note" : "photo";
    return this.send(memberName, { text: `[${kind}] ${file.fileName}` }, content);
  }

  // A threaded reply under `target`, which works as it does for react().
  reply(memberName: string, target: string, text: string): Promise<Exchange> {
    const under = this.findEntry(target);
    return this.send(memberName, { text, replyTo: under.id }, { type: "text", text }, {
      replyTo: { messageId: under.id },
    });
  }

  // The rest is called by the Spectrum platform below, not by commands.

  connect(deliver: Deliver): void {
    this.connection.resolve(deliver);
  }

  recordOutcome(outcome: MessageOutcome): void {
    this.waitingFor.get(outcome.id)?.(outcome);
  }

  // Lets the relay read a message it doesn't remember, as Linq's API does.
  recordedMessage(messageId: string): ProviderMessageRecord | undefined {
    const entry = this.transcript.find((candidate) => candidate.id === messageId);
    if (!entry) return undefined;
    return {
      id: entry.id,
      content: { type: "text", text: entry.text },
      direction: entry.from === "scout" ? "outbound" : "inbound",
      space: { id: this.chatId },
      timestamp: new Date(),
    };
  }

  async recordLinkCard(url: string, content: Content): Promise<ProviderMessageRecord> {
    const id = `m${this.transcript.length + 1}`;
    const card = await previewLinkCard(url, join(CARDS_FOLDER, `${this.chatId}-${id}`));
    const entry = this.addEntry({ from: "scout", text: url, card });
    return { id: entry.id, content, space: { id: this.chatId }, timestamp: new Date() };
  }

  recordScoutMessage(content: Content): ProviderMessageRecord {
    const entry = this.addEntry({ from: "scout", ...describeScoutContent(content) });
    return { id: entry.id, content, space: { id: this.chatId }, timestamp: new Date() };
  }

  // Waits until the bridge reports it has finished with the message, so the
  // replies are complete without waiting a fixed time.
  private async send(
    memberName: string,
    shownAs: Omit<ChatEntry, "id" | "from">,
    content: Content,
    extras: Pick<InboundRecord, "replyTo"> = {},
  ): Promise<Exchange> {
    const member = this.findMember(memberName);
    const deliver = await this.connection.promise;
    const sent = this.addEntry({ from: member.name, ...shownAs });
    const finished = new Promise<MessageOutcome>((resolve) => this.waitingFor.set(sent.id, resolve));

    await deliver({
      id: sent.id,
      content,
      sender: { id: member.phone },
      space: { id: this.chatId },
      timestamp: new Date(),
      ...extras,
    });
    const outcome = await finished;
    this.waitingFor.delete(sent.id);
    return { sent, outcome, replies: this.transcript.slice(this.transcript.indexOf(sent) + 1) };
  }

  private addEntry(fields: Omit<ChatEntry, "id">): ChatEntry {
    const entry = { id: `m${this.transcript.length + 1}`, ...fields };
    this.transcript.push(entry);
    return entry;
  }

  private findEntry(target: string): ChatEntry {
    if (/^m\d+$/.test(target)) {
      const entry = this.transcript.find((candidate) => candidate.id === target);
      if (!entry) throw new Error(`There's no message ${target} in this chat.`);
      return entry;
    }
    const scoutMessages = this.transcript.filter(
      (entry) => entry.from === "scout" && entry.tapback === undefined,
    );
    const words = target.toLowerCase();
    const entry =
      target === "scout.last"
        ? scoutMessages.at(-1)
        : scoutMessages.findLast((candidate) => candidate.text.toLowerCase().includes(words));
    if (!entry) throw new Error(`scout hasn't sent a message matching "${target}".`);
    return entry;
  }

  private findMember(name: string): ChatMember {
    const member = this.members.find((candidate) => candidate.name === name.toLowerCase());
    if (!member) {
      const names = this.members.map((candidate) => candidate.name).join(", ");
      throw new Error(`${name} isn't in this chat. Members: ${names}.`);
    }
    return member;
  }
}

export async function readMediaFile(path: string): Promise<MediaFile> {
  const file = Bun.file(path);
  if (!(await file.exists())) throw new Error(`There's no file at ${path}.`);
  const mimeType = IPHONE_MEDIA_TYPES[extname(path).toLowerCase()] ?? file.type;
  return { fileName: basename(path), mimeType, bytes: Buffer.from(await file.arrayBuffer()) };
}

function describeScoutContent(content: Content): Omit<ChatEntry, "id" | "from"> {
  switch (content.type) {
    case "text":
      return { text: content.text };
    case "reaction":
      return {
        text: `${content.emoji} on ${content.target.id}`,
        tapback: tapbackNamed(content.emoji) ?? content.emoji,
        on: content.target.id,
      };
    case "reply":
      return { ...describeScoutContent(content.content), replyTo: content.target.id };
    case "custom":
      return { text: describeHermesCard(content.raw as HermesCard) };
    default:
      return { text: `[${content.type}]` };
  }
}

// A card as the console shows it: its caption and subcaption, the text phones without the
// extension get, and why Linq would refuse to send it.
function describeHermesCard(card: HermesCard): string {
  const warnings = cardProblems(card).map((problem) => `⚠ ${problem}`);
  const thumbnail = `thumbnail ${card.thumbnail_url ?? "(none)"}`;
  const subcaption = card.subcaption ? [card.subcaption] : [];
  return [`🗂 card: ${card.caption}`, ...subcaption, thumbnail, ...warnings, card.fallback_text].join("\n");
}

// Spectrum only needs a message's id and content to aim a tapback at it.
function asMessageStub(entry: ChatEntry): Message {
  return { id: entry.id, content: { type: "text", text: entry.text } } as unknown as Message;
}

// Starts a Spectrum app whose only line is this chat, and runs the bridge's
// relay loop on it. Returns a function that stops both.
export async function connectDevChat(chat: DevChat): Promise<() => Promise<void>> {
  // Spectrum's start and stop notices would bury the chat in the terminal.
  setLogLevel("warn");
  const app = await Spectrum({ providers: [devchatPlatform(chat).config({})] });
  // Scripts and agents drive the console, so scout replies without pausing.
  // The console prints the chat itself, so only finished messages matter here.
  const report = { arrived: () => {}, finished: (outcome: MessageOutcome) => chat.recordOutcome(outcome) };
  const relay = relaySpectrumMessages(app, report, noTypingPause);
  return async () => {
    await app.stop();
    await relay;
  };
}

function devchatPlatform(chat: DevChat) {
  return definePlatform("devchat", {
    config: z.object({}),
    message: { schema: threadedReplySchema },
    user: { resolve: async ({ input }) => ({ id: input.userID }) },
    space: { create: async () => ({ id: chat.chatId }) },
    lifecycle: { createClient: async () => chat },
    messages: () =>
      stream<InboundRecord>((emit) => {
        chat.connect(emit);
      }),
    // Like Linq, the console knows everyone in the group, including members
    // who haven't texted yet.
    actions: {
      getMembers: async () => chat.members.map((member) => ({ id: member.phone })),
      getMessage: async (_, __, messageId) => chat.recordedMessage(messageId),
    },
    send: async ({ content }) =>
      content.type === "richlink"
        ? chat.recordLinkCard(content.url, content)
        : chat.recordScoutMessage(content),
  });
}

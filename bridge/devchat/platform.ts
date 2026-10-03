// The developer console's group chat: a Spectrum platform that plays a whole
// group from the terminal. Messages go through the bridge's real relay loop
// (spectrum.ts) to the real scout service. Only the iMessage line is fake.

import { basename } from "node:path";
import { Spectrum, definePlatform, stream, type Content } from "spectrum-ts";
import { asAttachment, setLogLevel, type ProviderMessageRecord } from "spectrum-ts/authoring";
import z from "zod";
import { relaySpectrumMessages } from "../spectrum";
import { tapbackNamed } from "../tapbacks";
import type { MessageOutcome } from "../trace";

export type ChatMember = { name: string; phone: string };

// One line of the chat. `from` is a member's name, or "scout". A tapback also
// names which one it was and the message it's on.
export type ChatEntry = {
  id: string;
  from: string;
  text: string;
  tapback?: string;
  on?: string;
};

// What happened to one member's message: the bridge's outcome, and scout's
// replies to it.
export type Exchange = { sent: ChatEntry; outcome: MessageOutcome; replies: ChatEntry[] };

export type Photo = { fileName: string; mimeType: string; bytes: Buffer };

type InboundRecord = {
  id: string;
  content: Content;
  sender: { id: string };
  space: { id: string };
  timestamp: Date;
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
    return this.send(memberName, text, { type: "text", text });
  }

  sendPhoto(memberName: string, photo: Photo): Promise<Exchange> {
    const content = asAttachment({
      name: photo.fileName,
      mimeType: photo.mimeType,
      read: async () => photo.bytes,
    });
    return this.send(memberName, `[photo] ${photo.fileName}`, content);
  }

  // The rest is called by the Spectrum platform below, not by commands.

  connect(deliver: Deliver): void {
    this.connection.resolve(deliver);
  }

  recordOutcome(outcome: MessageOutcome): void {
    this.waitingFor.get(outcome.id)?.(outcome);
  }

  recordScoutMessage(content: Content): ProviderMessageRecord {
    const entry =
      content.type === "reaction"
        ? this.addEntry({
            from: "scout",
            text: `${content.emoji} on ${content.target.id}`,
            tapback: tapbackNamed(content.emoji) ?? content.emoji,
            on: content.target.id,
          })
        : this.addEntry({
            from: "scout",
            text: content.type === "text" ? content.text : `[${content.type}]`,
          });
    return { id: entry.id, content, space: { id: this.chatId }, timestamp: new Date() };
  }

  // Waits until the bridge reports it has finished with the message, so the
  // replies are complete without waiting a fixed time.
  private async send(memberName: string, shownAs: string, content: Content): Promise<Exchange> {
    const member = this.findMember(memberName);
    const deliver = await this.connection.promise;
    const sent = this.addEntry({ from: member.name, text: shownAs });
    const finished = new Promise<MessageOutcome>((resolve) => this.waitingFor.set(sent.id, resolve));

    await deliver({
      id: sent.id,
      content,
      sender: { id: member.phone },
      space: { id: this.chatId },
      timestamp: new Date(),
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

  private findMember(name: string): ChatMember {
    const member = this.members.find((candidate) => candidate.name === name.toLowerCase());
    if (!member) {
      const names = this.members.map((candidate) => candidate.name).join(", ");
      throw new Error(`${name} isn't in this chat. Members: ${names}.`);
    }
    return member;
  }
}

export async function readPhoto(path: string): Promise<Photo> {
  const file = Bun.file(path);
  if (!(await file.exists())) throw new Error(`There's no photo at ${path}.`);
  // Bun doesn't know iPhone photos' type from the file name.
  const mimeType = path.toLowerCase().endsWith(".heic") ? "image/heic" : file.type;
  return { fileName: basename(path), mimeType, bytes: Buffer.from(await file.arrayBuffer()) };
}

// Starts a Spectrum app whose only line is this chat, and runs the bridge's
// relay loop on it. Returns a function that stops both.
export async function connectDevChat(chat: DevChat): Promise<() => Promise<void>> {
  // Spectrum's start and stop notices would bury the chat in the terminal.
  setLogLevel("warn");
  const app = await Spectrum({ providers: [devchatPlatform(chat).config({})] });
  const relay = relaySpectrumMessages(app, (outcome) => chat.recordOutcome(outcome));
  return async () => {
    await app.stop();
    await relay;
  };
}

function devchatPlatform(chat: DevChat) {
  return definePlatform("devchat", {
    config: z.object({}),
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
    },
    send: async ({ content }) => chat.recordScoutMessage(content),
  });
}

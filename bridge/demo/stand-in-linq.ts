// A stand-in for the parts of Linq's Partner API the demo commands use, so
// their tests send nothing real. It behaves like Linq's docs describe: chats
// come a page at a time, a new contact card starts inactive, and creating a
// group with the same members as an unnamed one sends to that one instead.

import type { ContactCard, DemoLine, LinqChat } from "./line";

export const SCOUT_NUMBER = "+15550000100";
// Small, so tests cross pages the way a busy line would.
const CHATS_PER_PAGE = 2;

export type SentMessage = { chatId: string; isFromScout: boolean; text: string };

export class StandInLinq {
  chats: LinqChat[] = [];
  messages: SentMessage[] = [];
  card: ContactCard | null = null;
  sharedCardWith: string[] = [];
  private server = Bun.serve({ hostname: "127.0.0.1", port: 0, fetch: (request) => this.answer(request) });
  private nextChatNumber = 1;

  get line(): DemoLine {
    return { api: { apiKey: "test-key", apiUrl: `http://127.0.0.1:${this.server.port}` }, scoutNumber: SCOUT_NUMBER };
  }

  stop(): void {
    this.server.stop(true);
  }

  // A phone's one-on-one chat with scout, as if the phone had texted it.
  addPrivateChat(phone: string, { hasScoutWritten = false } = {}): LinqChat {
    const chat = this.addChat({ phones: [phone], isGroup: false });
    this.messages.push({ chatId: chat.id, isFromScout: false, text: "hi" });
    if (hasScoutWritten) this.messages.push({ chatId: chat.id, isFromScout: true, text: "hey!" });
    return chat;
  }

  addGroup(phones: string[], { name = "", createdAt = new Date().toISOString() } = {}): LinqChat {
    return this.addChat({ phones, isGroup: true, name, createdAt });
  }

  messagesIn(chatId: string): SentMessage[] {
    return this.messages.filter((message) => message.chatId === chatId);
  }

  private addChat({
    phones,
    isGroup,
    name = "",
    createdAt = new Date().toISOString(),
  }: {
    phones: string[];
    isGroup: boolean;
    name?: string;
    createdAt?: string;
  }): LinqChat {
    const chat: LinqChat = {
      id: `chat-${this.nextChatNumber++}`,
      display_name: name,
      is_group: isGroup,
      created_at: createdAt,
      handles: [
        { handle: SCOUT_NUMBER, is_me: true, status: "active" },
        ...phones.map((handle) => ({ handle, is_me: false, status: "active" })),
      ],
    };
    this.chats.push(chat);
    return chat;
  }

  private async answer(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const route = `${request.method} ${url.pathname}`;
    const body = request.method === "GET" ? null : await request.text().then((text) => (text ? JSON.parse(text) : null));

    if (route === "GET /phone_numbers") {
      return Response.json({ phone_numbers: [{ phone_number: SCOUT_NUMBER }] });
    }
    if (route === "GET /chats") return this.listChats(Number(url.searchParams.get("cursor") ?? 0));
    if (route === "POST /chats") return this.createChat(body);
    if (route === "GET /contact_card") {
      if (!this.card) return Response.json({ error: { status: 404, code: 2012 } }, { status: 404 });
      return Response.json({ contact_cards: [this.card] });
    }
    if (route === "POST /contact_card") {
      this.card = { first_name: body.first_name, is_active: false };
      return Response.json(this.card);
    }

    const chatRoute = url.pathname.match(/^\/chats\/([^/]+)(\/.*)?$/);
    const chat = this.chats.find((candidate) => candidate.id === chatRoute?.[1]);
    if (!chat) return new Response("Not found", { status: 404 });
    const action = `${request.method} ${chatRoute?.[2] ?? ""}`;
    if (action === "GET /messages") {
      const messages = this.messagesIn(chat.id).map((message) => ({ is_from_me: message.isFromScout }));
      return Response.json({ messages });
    }
    if (action === "POST /messages") {
      this.messages.push({ chatId: chat.id, isFromScout: true, text: body.message.parts[0].value });
      return Response.json({ message: { id: `message-${this.messages.length}` } });
    }
    if (action === "POST /share_contact_card") {
      if (!this.card?.is_active) return Response.json({ error: { status: 404, code: 2012 } }, { status: 404 });
      this.sharedCardWith.push(chat.id);
      return new Response(null, { status: 204 });
    }
    if (action === "PUT ") {
      chat.display_name = body.display_name;
      return Response.json({ chat_id: chat.id, status: "pending" });
    }
    return new Response("Not found", { status: 404 });
  }

  private listChats(start: number): Response {
    const end = start + CHATS_PER_PAGE;
    return Response.json({
      chats: this.chats.slice(start, end),
      next_cursor: end < this.chats.length ? String(end) : null,
    });
  }

  private createChat(body: { from: string; to: string[]; message: { parts: { value: string }[] } }): Response {
    const members = [...body.to].sort().join(",");
    const reused = this.chats.find(
      (chat) =>
        chat.is_group &&
        !chat.display_name &&
        chat.handles
          .filter((handle) => !handle.is_me)
          .map((handle) => handle.handle)
          .sort()
          .join(",") === members,
    );
    const chat = reused ?? this.addChat({ phones: body.to, isGroup: true });
    this.messages.push({ chatId: chat.id, isFromScout: true, text: body.message.parts[0]!.value });
    return Response.json({ chat });
  }
}

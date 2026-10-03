// The demo line's chats and contact card, through Linq's Partner API.

import { callLinq, LinqApiError, type LinqApi, type LinqHandle } from "../linq-api";

// The most Linq returns at once.
const PAGE_SIZE = 100;

// scout's line: the API to call and the number it sends from.
export type DemoLine = { api: LinqApi; scoutNumber: string };

export type LinqChat = {
  id: string;
  display_name: string;
  is_group: boolean;
  created_at: string;
  handles: LinqHandle[];
};

export type ContactCard = { first_name: string; is_active: boolean };

// The demo needs one line, so an account with several numbers is a mistake to
// point out rather than guess at.
export async function findScoutNumber(api: LinqApi): Promise<string> {
  const { phone_numbers } = (await callLinq(api, "/phone_numbers")) as {
    phone_numbers: { phone_number: string }[];
  };
  const numbers = phone_numbers.map(({ phone_number }) => phone_number);
  if (numbers.length !== 1) {
    throw new Error(
      `The demo needs a Linq account with one number, and LINQ_API_KEY's account has ${numbers.length}: ${numbers.join(", ")}.`,
    );
  }
  return numbers[0]!;
}

export async function listChats(line: DemoLine): Promise<LinqChat[]> {
  const chats: LinqChat[] = [];
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ from: line.scoutNumber, limit: String(PAGE_SIZE) });
    if (cursor) query.set("cursor", cursor);
    const page = (await callLinq(line.api, `/chats?${query}`)) as {
      chats: LinqChat[];
      next_cursor?: string | null;
    };
    chats.push(...page.chats);
    cursor = page.next_cursor ?? null;
  } while (cursor);
  return chats;
}

// The phones in a chat, other than scout, that are still in it.
export function membersOf(chat: LinqChat): string[] {
  return chat.handles
    .filter((member) => !member.is_me && member.status === "active")
    .map((member) => member.handle);
}

// A phone's one-on-one chat with scout, which exists once the phone has texted
// scout: Linq's free lines can't text anyone first.
export function findPrivateChat(chats: LinqChat[], phone: string): LinqChat | null {
  return chats.find((chat) => !chat.is_group && membersOf(chat).includes(phone)) ?? null;
}

// Only the first page: a demo phone's private chat with scout is a few messages.
export async function hasScoutWritten(line: DemoLine, chatId: string): Promise<boolean> {
  const { messages } = (await callLinq(line.api, `/chats/${chatId}/messages?limit=${PAGE_SIZE}`)) as {
    messages: { is_from_me: boolean }[];
  };
  return messages.some((message) => message.is_from_me);
}

export async function sendText(line: DemoLine, chatId: string, text: string): Promise<void> {
  await callLinq(line.api, `/chats/${chatId}/messages`, {
    body: { message: { parts: [{ type: "text", value: text }] } },
  });
}

export async function findContactCard(line: DemoLine): Promise<ContactCard | null> {
  try {
    const query = new URLSearchParams({ phone_number: line.scoutNumber });
    const { contact_cards } = (await callLinq(line.api, `/contact_card?${query}`)) as {
      contact_cards: ContactCard[];
    };
    return contact_cards[0] ?? null;
  } catch (error) {
    // Linq answers 404 (error code 2012) when the line has no card.
    if (error instanceof LinqApiError && error.status === 404) return null;
    throw error;
  }
}

// Linq applies a new card to the line in the background, so it starts inactive.
export async function createContactCard(line: DemoLine, firstName: string): Promise<ContactCard> {
  return (await callLinq(line.api, "/contact_card", {
    body: { phone_number: line.scoutNumber, first_name: firstName },
  })) as ContactCard;
}

// Shows the chat's other member a prompt to save scout's name and photo. Linq
// needs scout to have written in the chat first.
export async function shareContactCard(line: DemoLine, chatId: string): Promise<void> {
  await callLinq(line.api, `/chats/${chatId}/share_contact_card`, { method: "POST" });
}

// The first message can't contain a link, which Linq refuses in a new chat.
export async function createGroup(line: DemoLine, phones: string[], firstMessage: string): Promise<LinqChat> {
  const { chat } = (await callLinq(line.api, "/chats", {
    body: {
      from: line.scoutNumber,
      to: phones,
      message: { parts: [{ type: "text", value: firstMessage }] },
    },
  })) as { chat: LinqChat };
  return chat;
}

export async function nameGroup(line: DemoLine, chatId: string, name: string): Promise<void> {
  await callLinq(line.api, `/chats/${chatId}`, { method: "PUT", body: { display_name: name } });
}

// Gets the demo phones ready for scout: each is allowed to text the line, has
// texted it once, and has been offered scout's contact card, so a group shows
// "scout" with its photo instead of a number.

import type { ContactList } from "./contacts";
import {
  createContactCard,
  findContactCard,
  findPrivateChat,
  hasScoutWritten,
  listChats,
  sendText,
  shareContactCard,
  type DemoLine,
  type LinqChat,
} from "./line";
import type { DemoPhone } from "./roster";

export const SCOUT_CONTACT_NAME = "scout";

export type PhoneSetup = {
  phone: DemoPhone;
  // Added to the shared line's contacts by this run.
  isNewContact: boolean;
  hasTexted: boolean;
  // scout said hi in their private chat by this run. Linq only shares a
  // contact card into a chat scout has written in.
  wasGreeted: boolean;
  wasSentCard: boolean;
};

export type SetupReport = {
  // Linq applies a new card in the background, so it can't be sent until then.
  isCardActive: boolean;
  phones: PhoneSetup[];
};

// Safe to run again: it only adds missing contacts and greets each phone once.
// It sends the card on every run, which Linq recommends (at most daily)
// because nobody can tell whether a phone saved it.
export async function setUpPhones(
  roster: DemoPhone[],
  line: DemoLine,
  contacts: ContactList | null,
): Promise<SetupReport> {
  const newContacts = contacts ? await addMissingContacts(roster, contacts) : [];
  const card = (await findContactCard(line)) ?? (await createContactCard(line, SCOUT_CONTACT_NAME));
  const chats = await listChats(line);

  const phones: PhoneSetup[] = [];
  // One phone at a time, so the line never sends a burst.
  for (const phone of roster) {
    const setup = await welcome(line, findPrivateChat(chats, phone.phone), {
      name: phone.name,
      canSendCard: card.is_active,
    });
    phones.push({ phone, isNewContact: newContacts.includes(phone.phone), ...setup });
  }
  return { isCardActive: card.is_active, phones };
}

async function addMissingContacts(roster: DemoPhone[], contacts: ContactList): Promise<string[]> {
  const existing = new Set(await contacts.list());
  const missing = roster.map(({ phone }) => phone).filter((phone) => !existing.has(phone));
  for (const phone of missing) await contacts.add(phone);
  return missing;
}

// Greets a phone that has texted scout, and offers it scout's contact card.
async function welcome(
  line: DemoLine,
  privateChat: LinqChat | null,
  { name, canSendCard }: { name: string; canSendCard: boolean },
): Promise<Pick<PhoneSetup, "hasTexted" | "wasGreeted" | "wasSentCard">> {
  if (!privateChat) return { hasTexted: false, wasGreeted: false, wasSentCard: false };
  const wasGreeted = !(await hasScoutWritten(line, privateChat.id));
  if (wasGreeted) await sendText(line, privateChat.id, greeting(name));
  if (canSendCard) await shareContactCard(line, privateChat.id);
  return { hasTexted: true, wasGreeted, wasSentCard: canSendCard };
}

function greeting(name: string): string {
  return `Hi ${name}, it's scout 👋 Save my contact card, so I show up by name when you add me to a group.`;
}

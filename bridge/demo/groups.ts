// The demo phones' group chats with scout: rehearsal groups the group command
// makes, and the one a member makes by hand on stage.

import { createGroup, findPrivateChat, listChats, membersOf, nameGroup, type DemoLine, type LinqChat } from "./line";
import type { DemoPhone } from "./roster";

// Newest first. A demo group is any group on scout's line whose members are
// all demo phones, so a group made by hand counts too.
export function findDemoGroups(chats: LinqChat[], roster: DemoPhone[]): LinqChat[] {
  const demoPhones = new Set(roster.map(({ phone }) => phone));
  return chats
    .filter((chat) => chat.is_group)
    .filter((chat) => {
      const members = membersOf(chat);
      return members.length > 0 && members.every((member) => demoPhones.has(member));
    })
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}

// Makes a new group of every demo phone plus scout, named "Rehearsal <n>".
export async function createRehearsalGroup(line: DemoLine, roster: DemoPhone[]): Promise<LinqChat> {
  const chats = await listChats(line);
  const notTexted = roster.filter(({ phone }) => !findPrivateChat(chats, phone));
  if (notTexted.length > 0) {
    const names = notTexted.map(({ name }) => name).join(", ");
    throw new Error(
      `scout can't add ${names} to a group until they've texted scout once. Run bun run demo setup to see who has.`,
    );
  }

  const name = `Rehearsal ${findDemoGroups(chats, roster).length + 1}`;
  const phones = roster.map(({ phone }) => phone);
  const group = await createGroup(line, phones, `${name} of scout's demo. Text anything to start.`);
  // Linq sends to an unnamed group with the same members instead of making a
  // new one. Renaming that group could rename the one used on stage.
  const existing = chats.find((chat) => chat.id === group.id);
  if (existing) {
    throw new Error(
      `Linq sent the first message to the existing group "${existing.display_name}" (${existing.id}) instead of making a new one. Give that group a name in Messages, then run this again.`,
    );
  }
  // Named, so the next run makes a fresh group instead of reusing this one.
  await nameGroup(line, group.id, name);
  return { ...group, display_name: name };
}

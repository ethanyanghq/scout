import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import type { ContactList } from "./contacts";
import type { ContactCard } from "./line";
import type { DemoPhone } from "./roster";
import { setUpPhones } from "./setup";
import { StandInLinq } from "./stand-in-linq";

const MAYA = { name: "Maya", phone: "+15550000001" };
const LEO = { name: "Leo", phone: "+15550000002" };
const JORDAN = { name: "Jordan", phone: "+15550000003" };
const ROSTER: DemoPhone[] = [MAYA, LEO, JORDAN];

// A shared line's contact list, kept in memory instead of through the CLI.
function contactList(phones: string[]): ContactList & { phones: string[] } {
  return {
    phones,
    list: async () => [...phones],
    add: async (phone) => {
      phones.push(phone);
    },
  };
}

let linq: StandInLinq;
beforeEach(() => {
  linq = new StandInLinq();
  linq.card = { first_name: "scout", is_active: true };
});
afterEach(() => linq.stop());

describe("getting the demo phones ready for scout", () => {
  test("adds the phones that aren't contacts yet to a shared line's contacts", async () => {
    const contacts = contactList([MAYA.phone]);

    const report = await setUpPhones(ROSTER, linq.line, contacts);

    expect(contacts.phones).toEqual([MAYA.phone, LEO.phone, JORDAN.phone]);
    expect(report.phones.map((setup) => setup.isNewContact)).toEqual([false, true, true]);
  });

  test("says hi to a phone that has texted scout, then sends it scout's contact card", async () => {
    const chat = linq.addPrivateChat(MAYA.phone);

    const report = await setUpPhones(ROSTER, linq.line, null);

    expect(linq.messagesIn(chat.id).at(-1)).toMatchObject({ isFromScout: true, text: expect.stringContaining("Maya") });
    expect(linq.sharedCardWith).toEqual([chat.id]);
    expect(report.phones[0]).toMatchObject({ hasTexted: true, wasGreeted: true, wasSentCard: true });
  });

  test("says hi to each phone only once, but sends the card again", async () => {
    const chat = linq.addPrivateChat(MAYA.phone, { hasScoutWritten: true });

    const report = await setUpPhones(ROSTER, linq.line, null);

    expect(linq.messagesIn(chat.id)).toHaveLength(2);
    expect(linq.sharedCardWith).toEqual([chat.id]);
    expect(report.phones[0]).toMatchObject({ wasGreeted: false, wasSentCard: true });
  });

  test("shows which phones haven't texted scout, and sends them nothing", async () => {
    linq.addPrivateChat(LEO.phone);
    linq.addPrivateChat(JORDAN.phone);

    const report = await setUpPhones(ROSTER, linq.line, null);

    expect(report.phones.map((setup) => [setup.phone.name, setup.hasTexted])).toEqual([
      ["Maya", false],
      ["Leo", true],
      ["Jordan", true],
    ]);
    expect(linq.messages.filter((message) => message.isFromScout)).toHaveLength(2);
  });

  test("finds every phone's chat however many chats scout's line has", async () => {
    linq.addGroup([MAYA.phone, LEO.phone, JORDAN.phone]);
    linq.addPrivateChat("+15550000009");
    linq.addPrivateChat(MAYA.phone);
    linq.addPrivateChat(LEO.phone);
    linq.addPrivateChat(JORDAN.phone);

    const report = await setUpPhones(ROSTER, linq.line, null);

    expect(report.phones.every((setup) => setup.hasTexted)).toBe(true);
  });

  test("creates scout's contact card when the line has none, and waits until Linq activates it to send it", async () => {
    linq.card = null;
    linq.addPrivateChat(MAYA.phone);

    const report = await setUpPhones(ROSTER, linq.line, null);

    // Read through its declared type: TypeScript still thinks it's the null set above.
    expect(linq.card as ContactCard | null).toEqual({ first_name: "scout", is_active: false });
    expect(report.isCardActive).toBe(false);
    expect(linq.sharedCardWith).toEqual([]);
    expect(report.phones[0]).toMatchObject({ wasGreeted: true, wasSentCard: false });
  });
});

import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import type { DemoPhone } from "./roster";
import { setUpPhones } from "./setup";
import { StandInLinq } from "./stand-in-linq";

const MAYA = { name: "Maya", phone: "+15550000001" };
const LEO = { name: "Leo", phone: "+15550000002" };
const JORDAN = { name: "Jordan", phone: "+15550000003" };
const ROSTER: DemoPhone[] = [MAYA, LEO, JORDAN];

let linq: StandInLinq;
beforeEach(() => {
  linq = new StandInLinq();
  linq.card = { first_name: "scout", is_active: true };
});
afterEach(() => linq.stop());

describe("getting the demo phones ready for scout", () => {
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
});

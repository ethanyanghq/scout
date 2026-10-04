import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { createRehearsalGroup } from "./groups";
import type { DemoPhone } from "./roster";
import { SCOUT_NUMBER, StandInLinq } from "./stand-in-linq";

const MAYA = { name: "Maya", phone: "+15550000001" };
const LEO = { name: "Leo", phone: "+15550000002" };
const JORDAN = { name: "Jordan", phone: "+15550000003" };
const ROSTER: DemoPhone[] = [MAYA, LEO, JORDAN];
const ROSTER_PHONES = ROSTER.map(({ phone }) => phone);

let linq: StandInLinq;
beforeEach(() => {
  linq = new StandInLinq();
});
afterEach(() => linq.stop());

function everyoneHasTexted(): void {
  for (const { phone } of ROSTER) linq.addPrivateChat(phone);
}

describe("making a rehearsal group", () => {
  test("makes a group of every demo phone plus scout, named Rehearsal 1", async () => {
    everyoneHasTexted();

    const group = await createRehearsalGroup(linq.line, ROSTER);

    const made = linq.chats.find((chat) => chat.id === group.id)!;
    expect(made.is_group).toBe(true);
    expect(made.display_name).toBe("Rehearsal 1");
    expect(made.handles.map(({ handle }) => handle)).toEqual([SCOUT_NUMBER, ...ROSTER_PHONES]);
    expect(group.display_name).toBe("Rehearsal 1");
  });

  test("won't make a group until every phone has texted scout", async () => {
    linq.addPrivateChat(MAYA.phone);
    linq.addPrivateChat(JORDAN.phone);

    await expect(createRehearsalGroup(linq.line, ROSTER)).rejects.toThrow("scout can't add Leo to a group");
    expect(linq.chats.filter((chat) => chat.is_group)).toEqual([]);
  });
});

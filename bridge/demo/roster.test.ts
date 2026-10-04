import { describe, expect, test } from "bun:test";
import { join } from "node:path";
import { loadRoster, parseRoster } from "./roster";

const MAYA = { name: "Maya", phone: "+15550000001" };
const LEO = { name: "Leo", phone: "+15550000002" };
const PRIYA = { name: "Priya", phone: "+15550000004" };

describe("reading the demo roster", () => {
  test("reads each phone's persona and number", () => {
    expect(parseRoster(JSON.stringify([MAYA, LEO, PRIYA]))).toEqual([MAYA, LEO, PRIYA]);
  });

  test("the example roster is a valid roster", async () => {
    const roster = await loadRoster(join(import.meta.dir, "roster.example.json"));

    expect(roster.map(({ name }) => name)).toEqual(["Maya", "Leo", "Jordan", "Priya"]);
  });

  test("needs at least three phones, so Apple lets a member add scout to their group", () => {
    expect(() => parseRoster(JSON.stringify([MAYA, LEO]))).toThrow("needs at least 3 phones");
  });
});

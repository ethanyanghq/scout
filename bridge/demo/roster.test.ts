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

  test("rejects a number that isn't in E.164 format", () => {
    const roster = [MAYA, LEO, { name: "Priya", phone: "(555) 000-0004" }];

    expect(() => parseRoster(JSON.stringify(roster))).toThrow("2.phone: must be in E.164 format");
  });

  test("needs at least three phones, so Apple lets a member add scout to their group", () => {
    expect(() => parseRoster(JSON.stringify([MAYA, LEO]))).toThrow("needs at least 3 phones");
  });

  test("rejects a number listed twice", () => {
    const roster = [MAYA, LEO, { name: "Priya", phone: MAYA.phone }];

    expect(() => parseRoster(JSON.stringify(roster))).toThrow("lists the same number twice");
  });

  test("says how to make the roster when there isn't one", async () => {
    await expect(loadRoster("/nonexistent/roster.json")).rejects.toThrow("Copy demo/roster.example.json");
  });
});

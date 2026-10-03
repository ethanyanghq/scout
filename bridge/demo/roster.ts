// The demo roster: each demo phone's persona and number. The real numbers live
// in demo/roster.json, which is git-ignored; roster.example.json shows the
// format with 555 numbers.

import { join } from "node:path";
import z from "zod";

export const ROSTER_FILE = join(import.meta.dir, "roster.json");
// Apple may only let a member add scout to a group of at least three others.
const MIN_PHONES = 3;
// A shared Linq line allows this many contacts, and every phone needs to be one.
const MAX_PHONES = 20;

export type DemoPhone = { name: string; phone: string };

const rosterSchema = z
  .array(
    z.object({
      name: z.string().min(1),
      phone: z.string().regex(/^\+[1-9]\d{6,14}$/, "must be in E.164 format, like +15551234567"),
    }),
  )
  .min(MIN_PHONES, `needs at least ${MIN_PHONES} phones besides scout`)
  .max(MAX_PHONES, `can have at most ${MAX_PHONES} phones, the shared line's contact limit`)
  .refine((phones) => new Set(phones.map(({ phone }) => phone)).size === phones.length, {
    message: "lists the same number twice",
  });

export async function loadRoster(path: string = ROSTER_FILE): Promise<DemoPhone[]> {
  const file = Bun.file(path);
  if (!(await file.exists())) {
    throw new Error(
      `There's no demo roster at ${path}. Copy demo/roster.example.json there and put in each demo phone's number.`,
    );
  }
  return parseRoster(await file.text());
}

export function parseRoster(text: string): DemoPhone[] {
  const parsed = rosterSchema.safeParse(JSON.parse(text));
  if (parsed.success) return parsed.data;
  const problems = parsed.error.issues.map((issue) => {
    const where = issue.path.length > 0 ? `${issue.path.join(".")}: ` : "";
    return `  ${where}${issue.message}`;
  });
  throw new Error(`The demo roster isn't right:\n${problems.join("\n")}`);
}

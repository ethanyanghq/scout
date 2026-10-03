// A shared Linq line's contact list: the up to 20 numbers allowed to text it.
// Linq manages the list through its CLI's own login, not the Partner API, so
// this runs the `linq` CLI. Dedicated lines have no contact list.

export type ContactList = {
  list(): Promise<string[]>;
  add(phone: string): Promise<void>;
};

// Null when the logged-in line is dedicated, so no contacts are needed.
export async function openContactList(): Promise<ContactList | null> {
  if (Bun.which("linq") === null) {
    throw new Error("Install the Linq CLI, which manages scout's contacts: npm i -g @linqapp/cli");
  }
  const whoami = (await runLinq(["whoami", "--json"])) as { line?: string };
  if (whoami.line !== "Shared") return null;
  return {
    list: async () => {
      const { contacts } = (await runLinq(["contacts", "list", "--json"])) as {
        contacts: { contactPhone: string }[];
      };
      return contacts.map((contact) => contact.contactPhone);
    },
    add: async (phone) => {
      await runLinq(["contacts", "add", phone, "--json"]);
    },
  };
}

async function runLinq(args: string[]): Promise<unknown> {
  const linq = Bun.spawn(["linq", ...args], { stdout: "pipe", stderr: "pipe" });
  const [output, errorOutput, exitCode] = await Promise.all([
    new Response(linq.stdout).text(),
    new Response(linq.stderr).text(),
    linq.exited,
  ]);
  if (exitCode !== 0) {
    throw new Error(`\`linq ${args.join(" ")}\` failed: ${(errorOutput || output).trim()}`);
  }
  return JSON.parse(output);
}

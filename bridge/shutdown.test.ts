import { describe, expect, test } from "bun:test";
import { stopAfterCtrlC } from "./shutdown";

// Behaves like `linq webhooks listen`: the first signal starts a slow cleanup,
// and any later signal exits on the spot, skipping it.
const RELAY_LIKE = `
let isCleaningUp = false;
const shutDown = async () => {
  if (isCleaningUp) process.exit(0);
  isCleaningUp = true;
  await Bun.sleep(200);
  console.log("webhook deleted");
  process.exit(0);
};
process.on("SIGINT", shutDown);
process.on("SIGTERM", shutDown);
console.log("listening");
setInterval(() => {}, 1000);
`;

async function startRelayLike() {
  const child = Bun.spawn([process.execPath, "-e", RELAY_LIKE], { stdout: "pipe" });
  const reader = child.stdout.getReader();
  const decoder = new TextDecoder();
  let output = "";
  while (!output.includes("listening")) output += decoder.decode((await reader.read()).value);
  const restOfOutput = (async () => {
    for (let chunk = await reader.read(); !chunk.done; chunk = await reader.read()) {
      output += decoder.decode(chunk.value);
    }
    return output;
  })();
  return { child, output: restOfOutput };
}

describe("stopping bun run dev with Ctrl-C", () => {
  test("lets the relay finish deleting its webhook instead of signaling it again", async () => {
    const relay = await startRelayLike();
    // What the terminal does on Ctrl-C.
    relay.child.kill("SIGINT");

    await stopAfterCtrlC([relay.child]);

    expect(await relay.output).toContain("webhook deleted");
  });

  test("stops a program still running once the grace period is over", async () => {
    const stubborn = Bun.spawn([process.execPath, "-e", "setInterval(() => {}, 1000)"]);

    await stopAfterCtrlC([stubborn], 50);

    expect(stubborn.killed).toBe(true);
  });
});

// How `bun run dev` stops the programs it started.
//
// Each signal counts. `linq webhooks listen` deletes its Linq webhook when the
// first signal arrives, but a second one makes it exit before that delete
// finishes. The webhook then stays behind, Linq keeps retrying every event to
// it, and the live relay's events arrive minutes late and out of order.

type Child = Pick<Bun.Subprocess, "exited" | "kill">;

// Long enough for the relay's one Linq API call, short enough that a stuck
// program doesn't hold up the terminal.
export const CTRL_C_GRACE_MS = 10_000;

// Ctrl-C in a terminal already sends SIGINT to every program started from it,
// so they're given time to finish on their own before anything is sent again.
export async function stopAfterCtrlC(children: Child[], graceMs = CTRL_C_GRACE_MS): Promise<void> {
  const allExited = Promise.all(children.map((child) => child.exited));
  const timedOut = Bun.sleep(graceMs).then(() => "timed out" as const);
  if ((await Promise.race([allExited, timedOut])) !== "timed out") return;
  await stopChildren(children);
}

// For every other stop (a crash, SIGTERM): one signal each, then wait.
export async function stopChildren(children: Child[]): Promise<void> {
  for (const child of children) child.kill();
  await Promise.all(children.map((child) => child.exited));
}

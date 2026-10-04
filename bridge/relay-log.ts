// Which lines of `linq webhooks listen` are worth showing in `bun run dev`.
// It prints a line for every event it forwards and its setup details; the
// bridge already logs each message, so only problems and status stay.

// "9:00:04 PM  message.received  → http://127.0.0.1:8788/linq-events  [204 No Content]  (11ms)"
const FORWARDED_OK = /→ \S+\s+\[2\d\d /;
// Setup details, including the webhook's signing secret, which never belongs in a log.
const SETUP_DETAILS = /^\s*(Signing secret|Events|Webhook created|Webhook ID|Forwarding to):/;

export function isWorthShowing(relayLine: string): boolean {
  if (relayLine.trim() === "") return false;
  return !FORWARDED_OK.test(relayLine) && !SETUP_DETAILS.test(relayLine);
}

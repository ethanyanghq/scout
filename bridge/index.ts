// Connects scout's Python service to iMessage, through Photon's Spectrum SDK
// or a Linq line.
//
// Photon can only send messages from TypeScript, so this bridge stays thin:
// it forwards each incoming text (and photo, such as a receipt) to scout over
// HTTP and sends back whatever scout replies. All of scout's logic lives in the Python service.
//
// Run with:  bun run index.ts
// Settings (Bun reads them from bridge/.env automatically):
//   IMESSAGE_MODE=local           Use this Mac's Messages account (no Photon plan).
//   IMESSAGE_MODE=cloud           Use a Photon cloud line; also set
//                                 PHOTON_PROJECT_ID and PHOTON_PROJECT_SECRET.
//   IMESSAGE_MODE=linq            Use a Linq line in group chats (no Apple ID);
//                                 also set LINQ_API_KEY. See linq.ts.
//   SCOUT_URL=http://127.0.0.1:8787   Where the Python service is listening.

import { Spectrum } from "spectrum-ts";
import { imessage } from "spectrum-ts/providers/imessage";
import { localIMessage } from "@spectrum-ts/imessage-local";
import { relayLinqGroupMessages } from "./linq";
import { SCOUT_URL } from "./scout";
import { relaySpectrumMessages } from "./spectrum";
import { logOutcome } from "./trace";

const mode = process.env.IMESSAGE_MODE ?? "local";
if (mode === "linq") {
  await relayLinqGroupMessages(requireSetting("LINQ_API_KEY"));
} else {
  const app = await connectToIMessage(mode);
  console.log(`scout bridge is listening for texts, forwarding to ${SCOUT_URL}`);
  await relaySpectrumMessages(app, logOutcome);
}

async function connectToIMessage(mode: string) {
  if (mode === "local") {
    return Spectrum({ providers: [localIMessage.config()] });
  }
  if (mode === "cloud") {
    return Spectrum({
      projectId: requireSetting("PHOTON_PROJECT_ID"),
      projectSecret: requireSetting("PHOTON_PROJECT_SECRET"),
      providers: [imessage.config()],
    });
  }
  throw new Error(`IMESSAGE_MODE must be "local", "cloud" or "linq", got "${mode}"`);
}

function requireSetting(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Set ${name} in bridge/.env`);
  return value;
}

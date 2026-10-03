// How the bridge hands a text to scout's Python service and gets replies back.

import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { $ } from "bun";

const DEFAULT_SCOUT_URL = "http://127.0.0.1:8787";
// Claude reads images up to about this many pixels on the long side; bigger
// photos only cost more to send.
const MAX_PHOTO_EDGE_PIXELS = 1568;

export type IncomingPhoto = {
  media_type: "image/jpeg";
  base64_data: string;
};

export type IncomingText = {
  space_id: string;
  sender_phone: string;
  text: string;
  sent_at: string;
  participant_phones: string[];
  photo: IncomingPhoto | null;
};

// Read on each call, so tests and the end-to-end runner can point the bridge
// at their own service.
export function scoutUrl(): string {
  return process.env.SCOUT_URL ?? DEFAULT_SCOUT_URL;
}

export async function askScout(text: IncomingText): Promise<string[]> {
  const response = await fetch(`${scoutUrl()}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(text),
  });
  if (!response.ok) {
    throw new Error(`scout returned ${response.status}: ${await response.text()}`);
  }
  const { replies } = (await response.json()) as { replies: string[] };
  return replies;
}

// iPhones send HEIC, which Claude can't read, so every photo goes through
// macOS's built-in `sips` to become a downsized JPEG.
export async function toJpeg(photoBytes: Buffer): Promise<IncomingPhoto> {
  const folder = await mkdtemp(join(tmpdir(), "scout-photo-"));
  try {
    // sips reads the format from the file's contents, so the name doesn't matter.
    const original = join(folder, "original");
    const converted = join(folder, "photo.jpg");
    await writeFile(original, photoBytes);
    await $`sips -s format jpeg -Z ${MAX_PHOTO_EDGE_PIXELS} ${original} --out ${converted}`.quiet();
    const jpeg = await readFile(converted);
    return { media_type: "image/jpeg", base64_data: jpeg.toString("base64") };
  } finally {
    await rm(folder, { recursive: true, force: true });
  }
}

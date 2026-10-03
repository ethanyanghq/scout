import { afterAll, describe, expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { previewLinkCard } from "./link-card";

// A tiny PNG's first bytes are enough to stand in for a card's picture.
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const PAGES: Record<string, string> = {
  "/open-graph": `<html><head>
    <title>Page title</title>
    <meta property="og:title" content="San Juan wins 🌴">
    <meta property="og:description" content="3 of 4 votes · Mar 14–20">
    <meta property="og:image" content="/card.png">
  </head><body><img src="/other.png"></body></html>`,
  "/twitter": `<html><head>
    <meta name="twitter:title" content="Tacos at Lote 23">
    <meta name="twitter:description" content="4 min walk">
    <meta name="twitter:image" content="/card.png">
  </head></html>`,
  "/plain": `<html><head><title> Old San Juan walking tour </title></head>
    <body><img src="card.png"><img src="/second.png"></body></html>`,
  "/bare": `<html><body>nothing to show</body></html>`,
  "/entities": `<html><head><title>Sign in to Access &amp; Edit</title>
    <meta property="og:description" content="Tacos &amp; tequila &#39;24 &#x1F32E;">
    <meta property="og:image" content="/card.png?size=large&amp;v=2"></head></html>`,
};
const site = Bun.serve({
  hostname: "127.0.0.1",
  port: 0,
  fetch(request) {
    const path = new URL(request.url).pathname;
    if (path.endsWith(".png")) return new Response(PNG, { headers: { "content-type": "image/png" } });
    const page = PAGES[path];
    return page
      ? new Response(page, { headers: { "content-type": "text/html" } })
      : new Response("gone", { status: 404 });
  },
});
const SITE = `http://127.0.0.1:${site.port}`;
const NOT_HTTPS = "Not HTTPS: Linq only builds previews for https:// links.";

const folder = await mkdtemp(join(tmpdir(), "scout-cards-"));
afterAll(async () => {
  site.stop(true);
  await rm(folder, { recursive: true, force: true });
});

describe("previewing a link card", () => {
  test("builds the card from Open Graph tags and saves its picture", async () => {
    const card = await previewLinkCard(`${SITE}/open-graph`, join(folder, "m1"));

    expect(card).toEqual({
      url: `${SITE}/open-graph`,
      title: "San Juan wins 🌴",
      description: "3 of 4 votes · Mar 14–20",
      imageUrl: `${SITE}/card.png`,
      imageFile: join(folder, "m1.png"),
      warnings: [NOT_HTTPS],
    });
    expect(new Uint8Array(await Bun.file(join(folder, "m1.png")).arrayBuffer())).toEqual(PNG);
  });

  test("falls back to Twitter Card tags", async () => {
    const card = await previewLinkCard(`${SITE}/twitter`, join(folder, "m2"));

    expect(card).toMatchObject({
      title: "Tacos at Lote 23",
      description: "4 min walk",
      imageUrl: `${SITE}/card.png`,
    });
  });

  test("falls back to the page's title and first image", async () => {
    const card = await previewLinkCard(`${SITE}/plain`, join(folder, "m3"));

    expect(card).toMatchObject({
      title: "Old San Juan walking tour",
      description: null,
      imageUrl: `${SITE}/card.png`,
    });
  });

  test("decodes the page's HTML entities, as iMessage shows them", async () => {
    const card = await previewLinkCard(`${SITE}/entities`, join(folder, "m7"));

    expect(card).toMatchObject({
      title: "Sign in to Access & Edit",
      description: "Tacos & tequila '24 🌮",
      imageUrl: `${SITE}/card.png?size=large&v=2`,
    });
  });

  test("warns when the card would have no title or picture", async () => {
    const card = await previewLinkCard(`${SITE}/bare`, join(folder, "m4"));

    expect(card.warnings).toEqual([
      NOT_HTTPS,
      "No title: the card would show only the link.",
      "No image: the card would have no picture.",
    ]);
  });

  test("warns when the page doesn't load", async () => {
    const card = await previewLinkCard(`${SITE}/missing`, join(folder, "m5"));

    expect(card.warnings).toEqual([NOT_HTTPS, "Couldn't load the page (HTTP 404), so there'd be no card."]);
  });

  test("warns when the link is longer than Linq allows", async () => {
    const longUrl = `${SITE}/open-graph?${"x".repeat(2100)}`;

    const card = await previewLinkCard(longUrl, join(folder, "m6"));

    expect(card.warnings).toContain(`The URL is ${longUrl.length} characters; Linq allows 2048.`);
  });
});

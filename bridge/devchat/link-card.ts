// What iMessage will show for a link scout sends on its own: a card built the
// way Linq builds it, from the page's Open Graph tags, then its Twitter Card
// tags, then its <title> and first image. The developer console uses it so a
// card can be checked before any phone sees it.

export type LinkCard = {
  url: string;
  title: string | null;
  description: string | null;
  imageUrl: string | null;
  // Where the card's picture was saved, for a person or AI agent to open.
  imageFile: string | null;
  // Anything Linq would refuse or show badly.
  warnings: string[];
};

// Linq's limit for a link part.
const MAX_URL_LENGTH = 2048;
const FETCH_TIMEOUT_MS = 5000;
const NAMED_ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
const IMAGE_EXTENSIONS: Record<string, string> = {
  "image/png": "png",
  "image/jpeg": "jpg",
  "image/gif": "gif",
  "image/webp": "webp",
};

// Saves the card's picture as `${imageFileStem}.png` (or .jpg, and so on).
export async function previewLinkCard(url: string, imageFileStem: string): Promise<LinkCard> {
  const card: LinkCard = { url, title: null, description: null, imageUrl: null, imageFile: null, warnings: [] };
  if (!url.startsWith("https://")) {
    card.warnings.push("Not HTTPS: Linq only builds previews for https:// links.");
  }
  if (url.length > MAX_URL_LENGTH) {
    card.warnings.push(`The URL is ${url.length} characters; Linq allows ${MAX_URL_LENGTH}.`);
  }

  const page = await fetchOrExplain(url);
  if (typeof page === "string") {
    card.warnings.push(`Couldn't load the page (${page}), so there'd be no card.`);
    return card;
  }
  const tags = await readPageTags(await page.text());
  card.title = tags.meta["og:title"] ?? tags.meta["twitter:title"] ?? tags.title;
  card.description = tags.meta["og:description"] ?? tags.meta["twitter:description"] ?? null;
  const image = tags.meta["og:image"] ?? tags.meta["twitter:image"] ?? tags.firstImage;
  card.imageUrl = image ? new URL(image, page.url || url).href : null;

  if (!card.title) card.warnings.push("No title: the card would show only the link.");
  if (!card.imageUrl) {
    card.warnings.push("No image: the card would have no picture.");
  } else {
    card.imageFile = await saveImage(card.imageUrl, imageFileStem, card.warnings);
  }
  return card;
}

type PageTags = { meta: Record<string, string>; title: string | null; firstImage: string | null };

async function readPageTags(html: string): Promise<PageTags> {
  const meta: Record<string, string> = {};
  let title = "";
  let firstImage: string | null = null;
  await new HTMLRewriter()
    .on("meta", {
      element(element) {
        const key = (element.getAttribute("property") ?? element.getAttribute("name"))?.toLowerCase();
        const content = element.getAttribute("content");
        if (key && content && !(key in meta)) meta[key] = decodeEntities(content);
      },
    })
    .on("title", {
      text(chunk) {
        title += chunk.text;
      },
    })
    .on("img", {
      element(element) {
        const source = element.getAttribute("src");
        firstImage ??= source === null ? null : decodeEntities(source);
      },
    })
    .transform(new Response(html))
    .text();
  return { meta, title: decodeEntities(title).trim() || null, firstImage };
}

// HTMLRewriter hands back text and attributes as written in the HTML, so
// "&amp;" would show up in a title where iMessage shows "&".
function decodeEntities(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (entity, name: string) => {
    if (name.startsWith("#x") || name.startsWith("#X")) {
      return String.fromCodePoint(Number.parseInt(name.slice(2), 16));
    }
    if (name.startsWith("#")) return String.fromCodePoint(Number.parseInt(name.slice(1), 10));
    return NAMED_ENTITIES[name.toLowerCase()] ?? entity;
  });
}

async function saveImage(imageUrl: string, fileStem: string, warnings: string[]): Promise<string | null> {
  const image = await fetchOrExplain(imageUrl);
  if (typeof image === "string") {
    warnings.push(`Couldn't download the image (${image}).`);
    return null;
  }
  const mimeType = image.headers.get("content-type")?.split(";")[0] ?? "";
  const file = `${fileStem}.${IMAGE_EXTENSIONS[mimeType] ?? "img"}`;
  await Bun.write(file, await image.arrayBuffer());
  return file;
}

// The response, or a short reason it couldn't be fetched.
async function fetchOrExplain(url: string): Promise<Response | string> {
  try {
    const response = await fetch(url, { signal: AbortSignal.timeout(FETCH_TIMEOUT_MS) });
    return response.ok ? response : `HTTP ${response.status}`;
  } catch (error) {
    return error instanceof Error ? error.message : String(error);
  }
}

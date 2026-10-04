// A HermesShare card as Linq sends it: an imessage_app part whose URL carries
// the layout. iMessage runs no HTML or JavaScript, so the layout is data that
// the Apple-signed extension draws as native views.

// What scout's service hands the bridge for a card (src/scout/outgoing.py).
export type HermesCard = {
  layout: unknown;
  caption: string;
  thumbnail_url: string | null;
  fallback_text: string;
};

// A card opens only in this exact build of the extension: the team's own
// HermesShare build, signed by Andrew Visconti's personal team. Every phone
// that should open cards needs this build installed.
const HERMES_APP = {
  name: "HermesShare",
  team_id: "XKX94F4LDN",
  bundle_id: "com.visconti.hermesshare.app.MessagesExtension",
} as const;
// Linq refuses a longer data: URL, so an over-stuffed card has to be trimmed
// rather than silently truncated.
const MAX_CARD_URL_CHARS = 16_384;

export function cardPart(card: HermesCard) {
  return {
    type: "imessage_app",
    app: HERMES_APP,
    url: cardUrl(card),
    fallback_text: card.fallback_text,
    // With it true, iOS runs the extension inside the bubble and the card
    // can't be opened full screen.
    interactive: false,
    layout: { caption: card.caption, image_url: card.thumbnail_url },
  };
}

// Why Linq would refuse to send the card, if it would.
export function cardProblems(card: HermesCard): string[] {
  const problems: string[] = [];
  if (!card.thumbnail_url?.startsWith("https://")) {
    problems.push("Linq sends a card only with an HTTPS thumbnail");
  }
  const urlLength = cardUrl(card).length;
  if (urlLength > MAX_CARD_URL_CHARS) {
    problems.push(`the card is ${urlLength} characters, over Linq's ${MAX_CARD_URL_CHARS}`);
  }
  return problems;
}

function cardUrl(card: HermesCard): string {
  const encoded = Buffer.from(JSON.stringify(card.layout)).toString("base64");
  return `data:application/json;base64,${encoded}`;
}

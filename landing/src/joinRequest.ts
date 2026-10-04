// Netlify Forms records any POST to the site that names a form it found in
// index.html at build time, so joining needs no backend of our own.
const NETLIFY_FORM_NAME = "join";

export type JoinRequest = {
  name: string;
  phone: string;
};

export async function sendJoinRequest(request: JoinRequest): Promise<void> {
  const response = await fetch("/", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ "form-name": NETLIFY_FORM_NAME, ...request }).toString(),
  });
  if (!response.ok) {
    throw new Error(`Netlify did not record the join request: it answered ${response.status}`);
  }
}

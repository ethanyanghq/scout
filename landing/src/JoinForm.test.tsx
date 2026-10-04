import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { JoinForm } from "./JoinForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function fillInAndSubmit(name: string, phone: string) {
  fireEvent.change(screen.getByLabelText("your name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("your phone number"), { target: { value: phone } });
  fireEvent.click(screen.getByRole("button", { name: "join the waitlist" }));
}

test("sends the name and phone number to Netlify's join form", async () => {
  const netlify = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
  vi.stubGlobal("fetch", netlify);
  render(<JoinForm />);

  fillInAndSubmit("Maya", "(555) 010-0142");
  await screen.findByRole("status");

  const [url, request] = netlify.mock.calls[0];
  expect(url).toBe("/");
  expect(request.method).toBe("POST");
  expect(Object.fromEntries(new URLSearchParams(request.body))).toEqual({
    "form-name": "join",
    name: "Maya",
    phone: "(555) 010-0142",
  });
});

test("tells the person by name that they are on the waitlist", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 200 })));
  render(<JoinForm />);

  fillInAndSubmit("Maya", "(555) 010-0142");

  const confirmation = await screen.findByRole("status");
  expect(confirmation.textContent).toBe("got it, maya. you’re on the waitlist.");
});

test("asks the person to try again when Netlify does not record the request", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(<JoinForm />);

  fillInAndSubmit("Maya", "(555) 010-0142");

  const error = await screen.findByRole("alert");
  expect(error.textContent).toBe("that didn’t go through. check your connection and try again.");
  expect(screen.getByRole("button", { name: "join the waitlist" })).toBeDefined();
});

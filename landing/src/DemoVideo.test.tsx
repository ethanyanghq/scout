import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { DemoVideo } from "./DemoVideo";

const YOUTUBE_SCRIPT = 'script[src="https://www.youtube.com/iframe_api"]';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  delete window.YT;
  document.querySelector(YOUTUBE_SCRIPT)?.remove();
});

test("asks YouTube for nothing until someone presses play", () => {
  render(<DemoVideo />);

  expect(screen.getByRole("button", { name: "watch the demo" })).toBeDefined();
  expect(document.querySelector(YOUTUBE_SCRIPT)).toBeNull();
  expect(document.querySelector("iframe")).toBeNull();
});

test("plays the demo on YouTube's player in place of the poster", async () => {
  const playVideo = vi.fn();
  const createPlayer = vi.fn(function (_slot, options) {
    options.events.onReady({ target: { playVideo } });
  });
  window.YT = { Player: createPlayer as unknown as NonNullable<typeof window.YT>["Player"] };
  render(<DemoVideo />);

  fireEvent.click(screen.getByRole("button", { name: "watch the demo" }));

  await waitFor(() => expect(screen.queryByRole("button", { name: "watch the demo" })).toBeNull());
  expect(createPlayer.mock.calls[0][1].videoId).toBe("K9avihlDf5E");
  expect(playVideo).toHaveBeenCalledOnce();
});

test("offers the video on YouTube when its player does not load", async () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(<DemoVideo />);

  fireEvent.click(screen.getByRole("button", { name: "watch the demo" }));
  fireEvent.error(document.querySelector(YOUTUBE_SCRIPT)!);

  const error = await screen.findByRole("alert");
  expect(error.textContent).toBe("the video didn’t load. watch it on youtube ↗");
  expect(screen.getByRole("link", { name: "watch it on youtube ↗" }).getAttribute("href")).toBe(
    "https://youtu.be/K9avihlDf5E",
  );
});

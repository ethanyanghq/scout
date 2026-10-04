import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { App } from "./App";

afterEach(cleanup);

test("links to scout's Devpost page", () => {
  render(<App />);

  const devpostLink = screen.getByRole("link", { name: /devpost/ });
  expect(devpostLink.getAttribute("href")).toBe("https://devpost.com/software/scout-pifctu");
});

test("links to scout's GitHub repository", () => {
  render(<App />);

  const githubLink = screen.getByRole("link", { name: /github/ });
  expect(githubLink.getAttribute("href")).toBe("https://github.com/ethanyanghq/scout");
});

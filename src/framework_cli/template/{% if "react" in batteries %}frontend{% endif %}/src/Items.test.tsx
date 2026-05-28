import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { Items } from "./Items";

afterEach(() => vi.restoreAllMocks());

test("renders fetched items", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify([{ id: 1, name: "alpha" }]), { status: 200 }),
  );
  render(<Items />);
  await waitFor(() => expect(screen.getByText("alpha")).toBeInTheDocument());
});

test("shows an error state on failure", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 500 }));
  render(<Items />);
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
});

import { afterEach, beforeEach, expect, test, vi } from "vitest";

// Capture the web-vitals callbacks so the test can fire a synthetic vital.
const vitalCbs: Record<string, (m: { name: string; value: number }) => void> = {};
vi.mock("web-vitals", () => ({
  onLCP: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.LCP = cb),
  onINP: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.INP = cb),
  onCLS: (cb: (m: { name: string; value: number }) => void) => (vitalCbs.CLS = cb),
}));

import { initRum } from "./rum";

let beacon: ReturnType<typeof vi.fn>;

beforeEach(() => {
  beacon = vi.fn(() => true);
  Object.defineProperty(navigator, "sendBeacon", { value: beacon, configurable: true });
});
afterEach(() => vi.restoreAllMocks());

function lastBeaconBody() {
  const [url, body] = beacon.mock.calls.at(-1)!;
  expect(url).toBe("/internal/rum");
  return JSON.parse(body as string);
}

test("emits a pageview with pathname and utm params, and flushes on pagehide", () => {
  window.history.replaceState({}, "", "/items?utm_source=google&secret=x");
  initRum();
  window.dispatchEvent(new Event("pagehide"));
  const payload = lastBeaconBody();
  const pv = payload.events.find((e: { kind: string }) => e.kind === "pageview");
  expect(pv.path).toBe("/items"); // pathname only — no query string
  expect(pv.params).toEqual({ utm_source: "google" }); // only utm_* captured
  expect(JSON.stringify(payload)).not.toContain("secret"); // non-utm dropped client-side
});

test("forwards a web vital as a bounded event", () => {
  initRum();
  vitalCbs.LCP({ name: "LCP", value: 1234 });
  window.dispatchEvent(new Event("pagehide"));
  const vital = lastBeaconBody().events.find((e: { kind: string }) => e.kind === "vital");
  expect(vital).toMatchObject({ kind: "vital", name: "lcp", value: 1234 });
});

test("records uncaught errors as a bounded type, never the message text", () => {
  initRum();
  window.dispatchEvent(new ErrorEvent("error", { message: "PII: a@b.co" }));
  window.dispatchEvent(new Event("pagehide"));
  const payload = lastBeaconBody();
  const err = payload.events.find((e: { kind: string }) => e.kind === "error");
  expect(err).toEqual({ kind: "error", type: "error" });
  expect(JSON.stringify(payload)).not.toContain("a@b.co"); // raw message never sent
});

import { onCLS, onINP, onLCP } from "web-vitals";

const ENDPOINT = "/internal/rum";

type RumEvent =
  | { kind: "vital"; name: string; value: number }
  | { kind: "error"; type: "error" | "unhandledrejection" }
  | {
      kind: "pageview";
      path: string;
      params: Record<string, string>;
      referrer: string | null;
    };

const buffer: RumEvent[] = [];

function utmParams(search: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of new URLSearchParams(search)) {
    if (k.startsWith("utm_")) out[k] = v; // backend re-applies the authoritative allowlist
  }
  return out;
}

function referrerHost(ref: string): string | null {
  if (!ref) return null;
  try {
    return new URL(ref).host || null; // host only — never the full referring URL
  } catch {
    return null;
  }
}

function flush(): void {
  if (buffer.length === 0) return;
  const body = JSON.stringify({ events: buffer.splice(0, buffer.length) });
  navigator.sendBeacon?.(ENDPOINT, body);
}

/** Wire RUM collection once, at app startup. Safe no-op if sendBeacon is unavailable. */
export function initRum(): void {
  onLCP((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));
  onINP((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));
  onCLS((m) => buffer.push({ kind: "vital", name: m.name.toLowerCase(), value: m.value }));

  window.addEventListener("error", () => buffer.push({ kind: "error", type: "error" }));
  window.addEventListener("unhandledrejection", () =>
    buffer.push({ kind: "error", type: "unhandledrejection" }),
  );

  buffer.push({
    kind: "pageview",
    path: window.location.pathname,
    params: utmParams(window.location.search),
    referrer: referrerHost(document.referrer),
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") flush();
  });
  window.addEventListener("pagehide", flush);
}

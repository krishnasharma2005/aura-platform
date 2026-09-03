import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { ApiClientError } from "./api-client";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * HTTP status phrases that some servers and every proxy hand back as the whole
 * error body. They are true and useless: "Not Found" tells the owner of a
 * dental practice nothing about what to do next.
 */
const BARE_STATUS_PHRASE =
  /^(not found|forbidden|unauthorized|bad request|internal server error|service unavailable|bad gateway|gateway timeout|conflict|unprocessable (entity|content)|too many requests|error)\.?$/i;

/**
 * The message to actually show a business owner.
 *
 * The API client already prefers the backend's own `error` field, and when the
 * backend has written a real sentence ("That email is already registered")
 * that sentence is the best thing we can say — so it wins. But an error body
 * that is only an HTTP status phrase, or a network failure with no body at
 * all, gets replaced by the caller's plain-language fallback. This is why a
 * missing endpoint used to render the word "Not Found" under "Your documents".
 */
export function errorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    const msg = err.message?.trim();
    if (msg && !BARE_STATUS_PHRASE.test(msg) && !/^Something went wrong \(\d+\)\.?$/.test(msg)) {
      return msg;
    }
  }
  return fallback;
}

export function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const diffMs = Date.now() - date.getTime();
  const diffSec = Math.round(diffMs / 1000);
  const diffMin = Math.round(diffSec / 60);
  const diffHr = Math.round(diffMin / 60);
  const diffDay = Math.round(diffHr / 24);

  if (diffSec < 45) return "just now";
  if (diffMin < 60) return `${diffMin}m ago`;
  if (diffHr < 24) return `${diffHr}h ago`;
  if (diffDay < 7) return `${diffDay}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function formatClockTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

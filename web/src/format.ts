import type { Band } from "./api";

// Same cut-offs as similarity_band() in sql/03_functions.sql.
export function bandOf(score: number): Band {
  return score >= 0.7 ? "near duplicate" : score >= 0.5 ? "similar" : score >= 0.35 ? "related" : "different";
}

export const BAND_CLASS: Record<Band, string> = {
  "near duplicate": "band-near",
  similar: "band-similar",
  related: "band-related",
  different: "band-different",
};

export const BAND_COLOR: Record<Band, string> = {
  "near duplicate": "var(--down)",
  similar: "var(--warn)",
  related: "var(--accent)",
  different: "var(--faint)",
};

const day = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });
const dayTime = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

export const formatDay = (iso: string) => day.format(new Date(iso));
export const formatDayTime = (iso: string) => dayTime.format(new Date(iso));
export const formatTime = (iso: string) => time.format(new Date(iso));

export function initials(name: string): string {
  const words = name.replace(/^(Prof|Dr)\.\s*/, "").split(/\s+/).filter((w) => /[A-Za-z]/.test(w));
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

// "Rohan" for students; staff keep their title, "Prof. S. Rao".
export function shortName(name: string, role: string): string {
  return role === "student" ? name.split(" ")[0] : name;
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

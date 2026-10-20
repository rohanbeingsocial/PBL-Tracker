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

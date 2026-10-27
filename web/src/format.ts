const day = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });
const dayTime = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const time = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit" });

export const formatDay = (iso: string) => day.format(new Date(iso));
export const formatDayTime = (iso: string) => dayTime.format(new Date(iso));
export const formatTime = (iso: string) => time.format(new Date(iso));

// A submission link's last date and time: "31 Oct 2026, 23:59".
const deadline = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
export const formatDeadline = (iso: string) => deadline.format(new Date(iso));

// The same moment as a datetime-local box takes it, in the browser's own time zone.
export function localInput(iso: string): string {
  const d = new Date(iso);
  const two = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}T${two(d.getHours())}:${two(d.getMinutes())}`;
}

export function initials(name: string): string {
  const words = name.replace(/^(Prof|Dr)\.\s*/, "").split(/\s+/).filter((w) => /[A-Za-z]/.test(w));
  return ((words[0]?.[0] ?? "") + (words.length > 1 ? words[words.length - 1][0] : "")).toUpperCase();
}

// "Rohan" for students; staff keep their title, "Prof. S. Rao".
export function shortName(name: string, role: string): string {
  return role === "student" ? name.split(" ")[0] : name;
}

export const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

// How many students a submission link takes per team, leader included: "teams of 2 to 4
// students". Empty when any size will do.
export function teamSize(min: number, max: number | null): string {
  if (max === null) return min > 1 ? `teams of at least ${min} students` : "";
  if (max === min) return `teams of ${plural(min, "student")}`;
  return min > 1 ? `teams of ${min} to ${max} students` : `teams of up to ${max} students`;
}

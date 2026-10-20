// Light or dark. The choice is kept in this browser; until someone picks one, the
// computer's own setting decides.
export type Theme = "light" | "dark";

export function savedTheme(): Theme {
  const stored = localStorage.getItem("theme");
  if (stored === "light" || stored === "dark") return stored;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme, remember = false) {
  document.documentElement.dataset.theme = theme;
  if (remember) localStorage.setItem("theme", theme);
}

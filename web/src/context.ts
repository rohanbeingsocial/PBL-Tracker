import { createContext, useContext } from "react";
import type { Account, Reference } from "./api";
import type { Path } from "./hooks";

export interface AppState {
  me: Account;
  ref: Reference;
  go: (to: Path) => void;
  toast: (message: string) => void;
  // Some pages change what the sidebar counts (the review queue).
  refreshCounts: () => void;
}

export const AppContext = createContext<AppState | null>(null);

export function useApp(): AppState {
  const state = useContext(AppContext);
  if (!state) throw new Error("useApp outside the signed-in app");
  return state;
}

// The small label above each page title.
export function eyebrow(me: Account): string {
  return me.is_admin ? "PBL coordinator" : me.role === "student" ? "Student" : "Faculty";
}

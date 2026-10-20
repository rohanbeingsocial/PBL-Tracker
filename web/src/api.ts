// Every call goes to the Python server under /api. The session cookie is HttpOnly,
// so this code never sees it; the browser sends it along by itself.

export type Role = "student" | "faculty";
export type Status = "submitted" | "approved" | "rejected";
export type Band = "near duplicate" | "similar" | "related" | "different";
export type ProjectType = "software" | "hardware" | "both";

export interface Account {
  user_id: number;
  role: Role;
  is_admin: boolean;
  name: string;
  login: string;
  prn: string | null;
  must_change_password: boolean;
}

export interface DemoAccount {
  login: string;
  name: string;
  role: Role | "admin";
  shows: string;
}

export interface Link {
  link_id: number;
  label: string;
  url: string;
}

export interface ProjectFile {
  file_id: number;
  kind: "report" | "ppt";
  file_name: string;
  size_bytes: number;
  uploaded_at: string;
}

export interface Project {
  project_id: number;
  title: string;
  abstract: string;
  academic_year: string;
  subject: string;
  subject_name: string;
  faculty_id: number;
  faculty: string;
  project_type: ProjectType;
  status: Status;
  review_note: string | null;
  decided_at: string | null;
  marks_public: boolean;
  members: string | null;
  member_ids: number[];
  tags: string[];
  links: Link[];
  files: ProjectFile[];
  created_at: string;
}

export interface Scored {
  similarity: number | null;
  band: Band | null;
}

export interface Closest extends Scored {
  closest_title: string | null;
  closest_year: string | null;
}

// GET /projects/{id}: the card plus what this person may see and do.
export interface ProjectDetail extends Project {
  marks: number | null;
  marks_hidden: boolean;
  max_marks: number;
  is_member: boolean;
  is_faculty: boolean;
  can_change: boolean;
  closest: (Closest & { closest_id: number | null }) | null;
}

export interface Subject {
  subject_id: number;
  code: string;
  name: string;
  max_marks: number;
}

export interface Reference {
  subjects: Subject[];
  faculty: { user_id: number; name: string }[];
  tags: { tag_id: number; name: string }[];
  years: string[];
  current_year: string;
}

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    const message =
      typeof detail === "string" ? detail
      : detail && typeof detail === "object" && "message" in detail ? String((detail as { message: string }).message)
      : Array.isArray(detail) ? "Some of the values aren't valid. Check the form."
      : "Something went wrong. Try again in a minute.";
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

// Set by the app: what to do when the server says the session is over.
let onSignedOut: (message: string) => void = () => {};
export function whenSignedOut(handler: (message: string) => void) {
  onSignedOut = handler;
}

async function send<T>(path: string, init: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Can't reach the server. Is it running?");
  }
  const data = response.headers.get("content-type")?.includes("json") ? await response.json() : null;
  if (!response.ok) {
    const error = new ApiError(response.status, data?.detail);
    if (response.status === 401 && !path.includes("sign-in")) onSignedOut(error.message);
    throw error;
  }
  return data as T;
}

export function api<T>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  return send<T>(path, {
    method: options.method ?? (options.body === undefined ? "GET" : "POST"),
    headers: options.body === undefined ? {} : { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

// A report or presentation goes up as the request body itself; its name and kind
// are in the query string.
export function upload<T>(projectId: number, kind: ProjectFile["kind"], file: File): Promise<T> {
  return send<T>(`/projects/${projectId}/files?${query({ kind, name: file.name })}`, {
    method: "POST",
    headers: { "Content-Type": file.type || "application/octet-stream" },
    body: file,
  });
}

// The submit form goes as multipart form data, with the report and presentation in it.
export function postForm<T>(path: string, form: FormData): Promise<T> {
  return send<T>(path, { method: "POST", body: form });
}

export function query(params: Record<string, string | string[] | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else if (value !== undefined && value !== "") search.append(key, String(value));
  }
  return search.toString();
}

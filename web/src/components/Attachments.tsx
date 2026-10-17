import { useRef, useState } from "react";
import { api, upload, type Project, type ProjectFile } from "../api";
import { useApp } from "../context";
import { formatDay } from "../format";
import { FILE_KIND } from "./ui";

const ACCEPT = { report: ".pdf,.docx", ppt: ".pptx,.pdf" };

function size(bytes: number): string {
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// Links and files of one project, for the team and its faculty member: add a link,
// upload the report or presentation, remove either.
export function Attachments({ p, onChanged }: { p: Project; onChanged: () => void }) {
  const { toast } = useApp();
  const [label, setLabel] = useState("GitHub");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pickers = { report: useRef<HTMLInputElement>(null), ppt: useRef<HTMLInputElement>(null) };

  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      toast(done);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function addLink() {
    if (!/^https?:\/\/\S+$/.test(url.trim())) return setError("A link has to start with https:// or http://.");
    run(() => api(`/projects/${p.project_id}/links`, { body: { label: label.trim() || "Link", url: url.trim() } }), "Link added.")
      .then(() => setUrl(""));
  }

  function sendFile(kind: ProjectFile["kind"], file: File | undefined) {
    if (!file) return;
    if (file.size > 20 * 1024 * 1024) return setError("Files can be at most 20 MB.");
    run(() => upload(p.project_id, kind, file), `${FILE_KIND[kind]} uploaded.`);
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="divided">
        {p.links.map((l) => (
          <div key={l.link_id} className="row" style={{ gap: 10, padding: "6px 0" }}>
            <span className="label-sm" style={{ width: 90 }}>{l.label}</span>
            <a className="link grow ellipsis small" href={l.url} target="_blank" rel="noopener noreferrer">{l.url}</a>
            <button className="link small" disabled={busy} onClick={() => run(() => api(`/links/${l.link_id}`, { method: "DELETE" }), "Link removed.")}>Remove</button>
          </div>
        ))}
        {p.files.map((f) => (
          <div key={f.file_id} className="row" style={{ gap: 10, padding: "6px 0" }}>
            <span className="label-sm" style={{ width: 90 }}>{FILE_KIND[f.kind]}</span>
            <a className="link grow ellipsis small" href={`/api/files/${f.file_id}`}>{f.file_name}</a>
            <span className="mono muted" style={{ fontSize: 11 }}>{size(f.size_bytes)} · {formatDay(f.uploaded_at)}</span>
            <button className="link small" disabled={busy} onClick={() => run(() => api(`/files/${f.file_id}`, { method: "DELETE" }), "File removed.")}>Remove</button>
          </div>
        ))}
        {!p.links.length && !p.files.length && <div className="small muted" style={{ padding: "6px 0" }}>No links or files yet.</div>}
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input" style={{ width: 120 }} value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} aria-label="Link label" />
        <input className="input grow" style={{ minWidth: 200 }} value={url} maxLength={300} onChange={(e) => setUrl(e.target.value)}
               placeholder="https://github.com/team/project" aria-label="Link URL" />
        <button className="btn" disabled={busy || !url.trim()} onClick={addLink}>Add link</button>
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        {(["report", "ppt"] as const).map((kind) => (
          <span key={kind}>
            <input ref={pickers[kind]} type="file" accept={ACCEPT[kind]} hidden
                   onChange={(e) => { sendFile(kind, e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn" disabled={busy} onClick={() => pickers[kind].current?.click()}>
              Upload {kind === "report" ? "report (PDF or Word)" : "presentation (PPTX or PDF)"}
            </button>
          </span>
        ))}
        {busy && <span className="small muted">Working…</span>}
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

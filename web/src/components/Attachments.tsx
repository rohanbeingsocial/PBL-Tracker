import { useRef, useState } from "react";
import { api, upload, type Project, type ProjectFile } from "../api";
import { useApp } from "../context";
import { FILE_KIND } from "./ui";

const ACCEPT = { report: ".pdf", ppt: ".pptx,.pdf" };

function size(bytes: number): string {
  return bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// Links and files of one project, for the team and its faculty member: add or remove a
// link, replace the report, upload, replace or remove the presentation.
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

  const has = (kind: ProjectFile["kind"]) => p.files.find((f) => f.kind === kind);
  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="divided">
        {p.links.map((l) => (
          <div key={l.link_id} className="row small" style={{ gap: 10, padding: "6px 0" }}>
            <span className="grow ellipsis">{l.label}: {l.url}</span>
            <button className="link small" disabled={busy} onClick={() => run(() => api(`/links/${l.link_id}`, { method: "DELETE" }), "Link removed.")}>Remove</button>
          </div>
        ))}
        {p.files.map((f) => (
          <div key={f.file_id} className="row small" style={{ gap: 10, padding: "6px 0" }}>
            <span className="grow ellipsis">{FILE_KIND[f.kind]}: {f.file_name} <span className="muted">({size(f.size_bytes)})</span></span>
            {f.kind === "ppt" && (
              <button className="link small" disabled={busy} onClick={() => run(() => api(`/files/${f.file_id}`, { method: "DELETE" }), "Presentation removed.")}>Remove</button>
            )}
          </div>
        ))}
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        <input className="input" style={{ width: 110 }} value={label} maxLength={40} onChange={(e) => setLabel(e.target.value)} aria-label="Link label" />
        <input className="input grow" style={{ minWidth: 160 }} value={url} maxLength={300} onChange={(e) => setUrl(e.target.value)}
               placeholder="https://..." aria-label="Link URL" />
        <button className="btn" disabled={busy || !url.trim()} onClick={addLink}>Add link</button>
      </div>
      <div className="row wrap" style={{ gap: 8 }}>
        {(["report", "ppt"] as const).map((kind) => (
          <span key={kind}>
            <input ref={pickers[kind]} type="file" accept={ACCEPT[kind]} hidden
                   onChange={(e) => { sendFile(kind, e.target.files?.[0]); e.target.value = ""; }} />
            <button className="btn" disabled={busy} onClick={() => pickers[kind].current?.click()}>
              {kind === "report" ? "Replace report (PDF)" : has("ppt") ? "Replace presentation" : "Upload presentation"}
            </button>
          </span>
        ))}
        {busy && <span className="small muted">Working…</span>}
      </div>
      {error && <div className="error-text" role="alert">{error}</div>}
    </div>
  );
}

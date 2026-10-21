import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { EventBus, LinkTarget, PDFLinkService, PDFViewer } from "pdfjs-dist/web/pdf_viewer.mjs";
import "pdfjs-dist/web/pdf_viewer.css";
import { Icon } from "./charts";

GlobalWorkerOptions.workerSrc = workerUrl;

const STEPS = [0.5, 0.67, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const MARGIN = 72;        // grey space left and right of the page, in pixels
const MAX_FIT = 1.5;      // fitting never blows a page up beyond this
const CSS_UNITS = 96 / 72;  // PDF points to CSS pixels, as PDF.js counts them

// The report as a paper: white pages one under the other on a plain background, text
// that can be selected and searched with Ctrl+F, and links that work. PDF.js draws the
// pages, so it looks the same in every browser instead of using each browser's own
// PDF viewer and its toolbar.
export function ReportViewer({ fileId, fileName }: { fileId: number; fileName: string }) {
  const container = useRef<HTMLDivElement>(null);
  const viewerEl = useRef<HTMLDivElement>(null);
  const viewer = useRef<PDFViewer | null>(null);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1);
  const [fit, setFit] = useState(true);
  const fitting = useRef(true);
  const pageWidth = useRef(0);   // width of page 1 at 100%, in CSS pixels
  const fitToWidth = useRef(() => {});
  const [error, setError] = useState<string | null>(null);
  const url = `/api/files/${fileId}?inline=true`;

  useEffect(() => {
    if (!container.current || !viewerEl.current) return;
    const eventBus = new EventBus();
    const links = new PDFLinkService({ eventBus, externalLinkTarget: LinkTarget.BLANK, externalLinkRel: "noopener noreferrer nofollow" });
    const v = new PDFViewer({ container: container.current, viewer: viewerEl.current, eventBus, linkService: links, removePageBorders: true });
    links.setViewer(v);
    viewer.current = v;
    const fitNow = () => {
      if (!fitting.current || !pageWidth.current || !container.current) return;
      const room = container.current.clientWidth - MARGIN;
      v.currentScale = Math.max(0.3, Math.min(MAX_FIT, room / pageWidth.current));
    };
    fitToWidth.current = fitNow;
    // PDF.js scrolls the first page flush to the top when the scale is set; start at the
    // very top instead, so the margin above the first page shows like the others.
    eventBus.on("pagesinit", () => {
      fitNow();
      requestAnimationFrame(() => container.current?.scrollTo({ top: 0 }));
    });
    eventBus.on("pagechanging", (e: { pageNumber: number }) => setPage(e.pageNumber));
    eventBus.on("scalechanging", (e: { scale: number }) => setScale(e.scale));

    let gone = false;
    setError(null);
    setPage(1);
    setFit(true);
    fitting.current = true;
    const task = getDocument({ url, withCredentials: true });
    task.promise.then((d) => {
      if (gone) return;
      setPages(d.numPages);
      return d.getPage(1).then((first) => {
        if (gone) return;
        pageWidth.current = first.getViewport({ scale: 1 }).width * CSS_UNITS;
        v.setDocument(d);
        links.setDocument(d);
      });
    }).catch(() => { if (!gone) setError("The report couldn't be opened."); });

    // Keep "fit to width" when the window or the side panel changes size.
    const resize = new ResizeObserver(fitNow);
    resize.observe(container.current);
    return () => {
      gone = true;
      resize.disconnect();
      void task.destroy();
      viewer.current = null;
    };
  }, [url]);

  function zoom(direction: 1 | -1) {
    const v = viewer.current;
    if (!v) return;
    const next = direction > 0 ? STEPS.find((s) => s > scale + 0.01) : [...STEPS].reverse().find((s) => s < scale - 0.01);
    if (next) {
      fitting.current = false;
      v.currentScale = next;
      setFit(false);
    }
  }
  function fitWidth() {
    fitting.current = true;
    fitToWidth.current();
    setFit(true);
  }
  function goTo(n: number) {
    if (viewer.current && n >= 1 && n <= pages) viewer.current.currentPageNumber = n;
  }

  return (
    <div className="paper">
      <div className="paper-bar">
        <Icon name="file" size={16} />
        <span className="paper-name ellipsis" title={fileName}>{fileName}</span>
        {pages > 0 && (
          <span className="paper-pages">
            <input key={page} className="input" aria-label="Page" defaultValue={page} inputMode="numeric"
                   onKeyDown={(e) => { if (e.key === "Enter") goTo(Number(e.currentTarget.value)); }}
                   onBlur={(e) => { e.currentTarget.value = String(page); }} />
            <span className="muted">of {pages}</span>
          </span>
        )}
        <div className="paper-tools">
          <button type="button" className="icon-btn" onClick={() => zoom(-1)} aria-label="Zoom out">−</button>
          <button type="button" className={`paper-zoom${fit ? " on" : ""}`} onClick={fitWidth} title="Fit to width">
            {Math.round(scale * 100)}%
          </button>
          <button type="button" className="icon-btn" onClick={() => zoom(1)} aria-label="Zoom in">+</button>
          <a className="btn" href={url} target="_blank" rel="noopener noreferrer">Open</a>
          <a className="btn" href={`/api/files/${fileId}`}>Download</a>
        </div>
      </div>
      <div className="paper-body">
        <div ref={container} className="paper-scroll">
          <div ref={viewerEl} className="pdfViewer" />
        </div>
        {error && <div className="paper-error muted">{error}</div>}
      </div>
    </div>
  );
}

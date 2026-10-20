"""One-page PDF reports for the sample projects, so the project page has a report to
show. Written by hand (a PDF is plain text plus a table of byte offsets), so no PDF
library is needed. Real reports are uploaded by the teams."""
import textwrap

PAGE_WIDTH, PAGE_HEIGHT, MARGIN = 595, 842, 56      # A4 in points


def _escape(text: str) -> bytes:
    # Helvetica in a PDF uses the Windows-1252 character set; anything else becomes '?'.
    raw = text.encode("cp1252", errors="replace")
    return raw.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _pdf(lines: list[tuple[str, str, int]]) -> bytes:
    """lines: (font, text, size) from the top of the page down. font is F1 or F2 (bold)."""
    y = PAGE_HEIGHT - MARGIN
    stream = b""
    for font, text, size in lines:
        y -= size + 6
        stream += b"BT /%s %d Tf %d %d Td (%s) Tj ET\n" % (font.encode(), size, MARGIN, y, _escape(text))

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>" % (PAGE_WIDTH, PAGE_HEIGHT),
        b"<< /Length %d >>\nstream\n%sendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return out


def report(title: str, year: str, subject: str, faculty: str, team: list[str], abstract: str) -> bytes:
    lines = [("F2", line, 18) for line in textwrap.wrap(title, 48)]
    lines += [("F1", "", 6),
              ("F1", f"{subject}, {year}", 11),
              ("F1", f"Guided by {faculty}", 11),
              ("F1", "", 6),
              ("F2", "Team", 12)]
    lines += [("F1", name, 11) for name in team or ["(not recorded)"]]
    lines += [("F1", "", 6), ("F2", "Abstract", 12)]
    lines += [("F1", line, 11) for line in textwrap.wrap(abstract, 90)]
    lines += [("F1", "", 10), ("F1", "Sample report made for the demo data. The team's own report replaces it.", 9)]
    return _pdf(lines)

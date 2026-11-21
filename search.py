#!/usr/bin/env python3
"""
search.py — Local search page over db/archive.db (OCR'd magazine pages).

Usage:
    python3 search.py            # then open http://127.0.0.1:8000
    python3 search.py --port 8080
"""

import argparse
import html
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlencode

DB_PATH = Path(__file__).parent / "db" / "archive.db"
LIMIT = 100
HI_START, HI_END = "\x02", "\x03"  # placeholders, swapped for <mark> after escaping

CSS = """
body{font-family:-apple-system,"Hiragino Sans",sans-serif;max-width:1100px;margin:2em auto;padding:0 1em;color:#222}
form{display:flex;gap:.5em;margin-bottom:1.5em}input{flex:1;font-size:1.2em;padding:.4em}button{font-size:1.1em}
.hit{display:flex;gap:1em;border-bottom:1px solid #ddd;padding:.8em 0}.hit img{width:110px;border:1px solid #ccc}
.meta{color:#666;font-size:.9em}mark{background:#ffe066}a{color:#0645ad;text-decoration:none}
.page{display:flex;gap:1.5em;align-items:flex-start}.page img{width:55%;border:1px solid #ccc}
.page pre{white-space:pre-wrap;font-family:inherit;flex:1}
"""


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def highlight(text: str) -> str:
    return html.escape(text).replace(HI_START, "<mark>").replace(HI_END, "</mark>")


def like_snippet(text: str, q: str, width: int = 40) -> str:
    i = text.lower().find(q.lower())
    start, end = max(0, i - width), i + len(q) + width
    return ("…" if start else "") + text[start:i] + HI_START + text[i:i + len(q)] + HI_END + text[i + len(q):end] + "…"


def search(q: str) -> list[dict]:
    sql_cols = "p.id, p.issue_id, p.page_number, m.name_original AS magazine, i.issue_number, i.release_date"
    joins = "JOIN issues i ON i.id = p.issue_id JOIN magazines m ON m.id = i.magazine_id"
    with db() as conn:
        if len(q) >= 3:
            fts_q = '"' + q.replace('"', '""') + '"'  # phrase query: user input never parsed as FTS syntax
            rows = conn.execute(f"""
                SELECT {sql_cols}, snippet(fts_pages, 0, ?, ?, '…', 24) AS snip
                FROM fts_pages JOIN pages p ON p.id = fts_pages.rowid {joins}
                WHERE fts_pages MATCH ? ORDER BY p.issue_id, p.page_number LIMIT ?
            """, (HI_START, HI_END, fts_q, LIMIT)).fetchall()
            return [dict(r) for r in rows]
        # shortcut: trigram index needs >= 3 chars, so 1–2 char terms do a full scan; fine until ~100k pages
        rows = conn.execute(f"""
            SELECT {sql_cols}, p.ocr_full_text FROM pages p {joins}
            WHERE instr(lower(p.ocr_full_text), lower(?)) > 0 ORDER BY p.issue_id, p.page_number LIMIT ?
        """, (q, LIMIT)).fetchall()
        return [dict(r) | {"snip": like_snippet(r["ocr_full_text"], q)} for r in rows]


def layout(title: str, body: str, q: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>{CSS}</style></head><body>
<form action="/"><input name="q" value="{html.escape(q)}" placeholder="ファミコン, Gradius, Hudson…" autofocus aria-label="Search">
<button>Search</button></form>{body}</body></html>"""


def label(r) -> str:
    date = f" ({r['release_date']})" if r["release_date"] else ""
    return html.escape(f"{r['magazine']} #{r['issue_number']}{date} — p.{r['page_number']}")


def results_page(q: str) -> str:
    if not q:
        with db() as conn:
            n = conn.execute("SELECT count(*) FROM pages").fetchone()[0]
        return layout("Magazine search", f"<p class=meta>{n} pages indexed.</p>")
    hits = search(q)
    more = f" (first {LIMIT})" if len(hits) == LIMIT else ""
    items = "".join(
        f"""<div class=hit><a href="/page?{urlencode({'id': r['id'], 'q': q})}"><img src="/img?id={r['id']}" loading="lazy" alt=""></a>
        <div><a href="/page?{urlencode({'id': r['id'], 'q': q})}">{label(r)}</a><p>{highlight(r['snip'])}</p></div></div>"""
        for r in hits
    )
    return layout(f"{q} — search", f"<p class=meta>{len(hits)} page{'s' if len(hits) != 1 else ''}{more}</p>{items}", q)


def detail_page(page_id: int, q: str) -> str | None:
    with db() as conn:
        r = conn.execute("""
            SELECT p.id, p.page_number, p.ocr_full_text, m.name_original AS magazine, i.issue_number, i.release_date
            FROM pages p JOIN issues i ON i.id = p.issue_id JOIN magazines m ON m.id = i.magazine_id WHERE p.id = ?
        """, (page_id,)).fetchone()
    if not r:
        return None
    text = r["ocr_full_text"] or ""
    if q:
        text = text.replace(q, HI_START + q + HI_END)
    return layout(label(r), f"""<h2>{label(r)}</h2><div class=page>
        <a href="/img?id={r['id']}"><img src="/img?id={r['id']}" alt="Scan of page {r['page_number']}"></a>
        <pre>{highlight(text)}</pre></div>""", q)


class Handler(BaseHTTPRequestHandler):
    def send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        q = params.get("q", "").strip()
        try:
            page_id = int(params.get("id", "0"))
        except ValueError:
            page_id = 0

        if url.path == "/":
            return self.send(200, results_page(q).encode(), "text/html; charset=utf-8")
        if url.path == "/page":
            out = detail_page(page_id, q)
            if out:
                return self.send(200, out.encode(), "text/html; charset=utf-8")
        if url.path == "/img":
            # Image path comes from the DB row, never from the URL, so no path traversal.
            with db() as conn:
                row = conn.execute("SELECT image_path FROM pages WHERE id = ?", (page_id,)).fetchone()
            if row and row[0] and Path(row[0]).is_file():
                return self.send(200, Path(row[0]).read_bytes(), "image/jpeg")
        self.send(404, b"Not found", "text/plain")


def main() -> None:
    p = argparse.ArgumentParser(description="Local search page for the magazine archive.")
    p.add_argument("--port", type=int, default=8000)
    port = p.parse_args().port
    print(f"🔍 Searching {DB_PATH}\n   Open http://127.0.0.1:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()

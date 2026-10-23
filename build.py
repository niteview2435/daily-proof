#!/usr/bin/env python3
"""Generate the daily-proof static site into docs/.

Sources live in proofs/YYYY-MM-DD.md. Each becomes docs/YYYY-MM-DD.html where
the proposition and the proof each fade in as one group on scroll. Math is
written as $...$ / $$...$$ and rendered client-side by MathJax, so this script
needs only the standard library.
"""

import html
import http.server
import json
import re
import shutil
import sys
import threading
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "proofs"
OUT = ROOT / "docs"
ASSETS = ROOT / "assets"
THEME_MAP = ROOT / "theme_map.json"

MATHJAX_CDN = "https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
# Latin Modern — the typeface modern (Lua)LaTeX actually ships. Roman for body
# text, Sans for the gothic headings.
LM_BASE = "https://cdn.jsdelivr.net/gh/sugina-dev/latin-modern-web@1.0.1/style"
LM_ROMAN_CSS = f"{LM_BASE}/latinmodern-roman.css"
LM_SANS_CSS = f"{LM_BASE}/latinmodern-sans.css"


# --- tiny markdown -----------------------------------------------------------
# Just enough for prose proofs: paragraphs, unordered lists, bold/italic/code.
# Math spans are protected beforehand so markdown never mangles them.

MATH_RE = re.compile(r"(\$\$.+?\$\$|\$[^$\n]+?\$)", re.S)


def protect_math(text):
    store = []

    def repl(m):
        store.append(m.group(1))
        return f"\x00M{len(store) - 1}\x00"

    return MATH_RE.sub(repl, text), store


def restore_math(text, store):
    # Escape <, >, & inside the raw TeX so the browser doesn't read e.g. `$a<b$`
    # as an opening tag. MathJax reads the decoded DOM text, so it still sees the
    # original characters. & must be replaced first.
    for i, raw in enumerate(store):
        esc = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        text = text.replace(f"\x00M{i}\x00", esc)
    return text


def inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


# Japanese runs (kana / kanji / full-width punctuation & forms) get wrapped so
# CSS can tint them darker than the lighter Latin Modern Roman they sit beside —
# the font-family fallback alone can't colour per script. Half-width Latin,
# digits, symbols and math stay the body default. Covers CJK symbols/punctuation
# (、。「」々…), hiragana, katakana (+ー), CJK ideographs (incl. ext-A), and
# full-width forms. Run on the final HTML: generated tags hold no CJK, and the
# ASCII math placeholders (\x00M…\x00) never match, so this can't corrupt either.
JP_RE = re.compile(
    r"[　-〿぀-ゟ゠-ヿ㐀-䶿一-鿿＀-￯]+"
)


def wrap_jp(s):
    return JP_RE.sub(r'<span class="jp">\g<0></span>', s)


def md_to_html(text):
    text, store = protect_math(text)
    # Escape prose <, >, & now (math is already out as placeholders) so body
    # text and inline code can contain them safely; math is escaped on restore.
    text = html.escape(text, quote=False)
    out = []
    para = []
    items = None

    def flush_para():
        if para:
            out.append("<p>" + inline(" ".join(para).strip()) + "</p>")
            para.clear()

    def flush_list():
        nonlocal items
        if items is not None:
            out.append("<ul>" + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            items = None

    for line in text.split("\n"):
        line = line.rstrip()
        if re.match(r"^\s*([-*_])\1{2,}\s*$", line):
            # A rule line (---, ***, ___) just ends the current block; no <hr>
            # is drawn. Lets stray separators in pasted drafts stay harmless.
            flush_para()
            flush_list()
        elif re.match(r"^\s*-\s+", line):
            flush_para()
            if items is None:
                items = []
            items.append(inline(re.sub(r"^\s*-\s+", "", line)))
        elif line.strip() == "":
            flush_para()
            flush_list()
        elif items is not None:
            # Lazy continuation: a non-blank line under an open list extends the
            # current item (proofs often run a bullet across several lines).
            items[-1] += " " + inline(line.strip())
        else:
            para.append(line.strip())
    flush_para()
    flush_list()
    return restore_math(wrap_jp("\n".join(out)), store)


# --- source parsing ----------------------------------------------------------

# Section headings recognised in a day file, in rough document order of use.
# Any sequence of these may appear; same-kind repeats are auto-numbered.
SECTION_KINDS = ("定義", "公理", "補題", "命題", "定理", "証明", "例", "系", "注意")
# A heading is `# <kind>`, optionally followed by a one-line caption on the same
# line (`# 命題 相対位相の閉集合の特徴づけ`). The caption is shown only on theme
# pages (next to the label); day pages ignore it. A kind must be followed by
# whitespace or end-of-line, so `# 命題の一般化` stays a non-heading as before.
SECTION_RE = re.compile(
    r"(?m)^#\s+(" + "|".join(SECTION_KINDS) + r")(?:[ \t　]+(\S.*?))?[ \t　]*$"
)


def parse(text):
    """Return a list of (kind, caption, content) sections in document order.

    A day file may hold any sequence of the recognised `# <kind>` headings
    (see SECTION_KINDS) — e.g. 定義 / 命題 / 証明 / 例, each with an optional
    caption on the heading line. Empty sections (a heading with no body) are
    dropped. Repeats of the same kind are numbered later at render time.
    """
    body = text.strip()
    parts = SECTION_RE.split(body)
    rest = iter(parts[1:])  # (kind, caption, content) triples

    sections = []
    for kind, caption, content in zip(rest, rest, rest):
        content = content.strip()
        if content:
            sections.append((kind, (caption or "").strip(), content))
    return sections


def parse_tags(text):
    """Read a leading `tags:` line (before the first section) into a list."""
    for line in text.strip().splitlines():
        line = line.strip()
        if line.startswith("#"):
            break  # reached a section heading; no tags line above it
        if line.startswith("tags:"):
            raw = line[len("tags:"):]
            return [t for t in re.split(r"[,、\s]+", raw.strip()) if t]
    return []


def render_sections(sections, eyebrow_html="", with_divider=True, show_captions=False):
    """Build the stacked <section>s for a group of sections.

    Each (kind, content) section becomes one fade-in block. A kind that occurs
    more than once in the group is numbered (`命題 1`, `命題 2`, …); a lone kind
    is left unnumbered. 証明 blocks get a trailing ∎. `eyebrow_html` (a date, or
    a link back to the source day) is placed above the first block; the divider
    rides in the last block when `with_divider` is set.

    Tags are intentionally not rendered — they live in index.json only, for
    sorting/filtering later.
    """
    totals = {}
    for kind, _, _ in sections:
        totals[kind] = totals.get(kind, 0) + 1

    out = []
    first = [True]
    seen = {}

    def eyebrow():
        if not first[0]:
            return ""
        first[0] = False
        if not eyebrow_html:
            return ""
        return f'<p class="eyebrow">{eyebrow_html}</p>\n      '

    for kind, caption, content in sections:
        if totals[kind] > 1:
            seen[kind] = seen.get(kind, 0) + 1
            label = f"{kind} {seen[kind]}"
        else:
            label = kind
        # The heading's caption (a one-line gloss of what the item is) rides next
        # to the label — shown only on theme pages, hidden on day pages.
        if show_captions and caption:
            label += f'<span class="caption">{html.escape(caption, quote=False)}</span>'
        # ∎ as LaTeX (\blacksquare) so MathJax typesets it in the same font as
        # the rest of the math, not a raw Unicode glyph from the body font.
        qed = '\n      <p class="qed">$\\blacksquare$</p>' if kind == "証明" else ""
        out.append(
            '<section class="block reveal">\n'
            f"      {eyebrow()}<h2 class=\"label\">{label}</h2>\n"
            f'      <div class="body">{md_to_html(content)}</div>'
            f"{qed}\n"
            "    </section>"
        )

    # The divider rides along in the last block so it fades in together with
    # the final proof; the calendar reveals separately below it.
    if out and with_divider:
        idx = out[-1].rindex("</section>")
        out[-1] = (
            out[-1][:idx]
            + '  <hr class="divider" aria-hidden="true" />\n    </section>'
        )
    return "\n\n    ".join(out)


# A "lead" heading opens a new logical item; a 証明/例/注意 that follows attaches
# to the item above it. Splitting a day on these boundaries lets one day's file
# contribute several items to *different* theme articles (命題ごとに分割).
LEAD_KINDS = ("定義", "公理", "補題", "命題", "定理", "系")


def split_clusters(sections):
    """Group a day's sections into items: each lead heading starts a new item;
    trailing 証明/例/注意 stay with the item above. Returns a list of section
    lists, in document order."""
    clusters = []
    cur = []
    for section in sections:
        kind = section[0]
        if kind in LEAD_KINDS and cur:
            clusters.append(cur)
            cur = []
        cur.append(section)
    if cur:
        clusters.append(cur)
    return clusters


def assign_days_into_themes(d, sections, assign, slugs, theme_items):
    """Split one day into items and file each under its theme.

    `assign[d]` is a single theme name (the whole day) or a list of names, one
    per item in document order; a single name is broadcast to every item. Each
    item's own caption travels with its heading (shown on the theme page).
    Unknown theme names or a length mismatch are hard errors; an unassigned day
    is skipped with a warning (its day page is unaffected).
    """
    if d not in assign:
        print(f"  warning: {d} has no theme in theme_map.json — skipped")
        return
    clusters = split_clusters(sections)
    if not clusters:
        return
    names = assign[d]
    if isinstance(names, str):
        names = [names] * len(clusters)
    if len(names) != len(clusters):
        raise SystemExit(
            f"{d}: theme_map has {len(names)} theme(s) but the day splits into "
            f"{len(clusters)} item(s); list one theme per item (or a single one)"
        )
    for name, cluster in zip(names, clusters):
        if name not in slugs:
            raise SystemExit(f"{d}: unknown theme '{name}' (add it to themes[])")
        theme_items[name].append((d, cluster))


def render_theme(items):
    """Render a theme article: each item is one day's cluster, captioned by its
    heading gloss. `items` is (date, sections) oldest first — no source-day link
    and no dividers, just the stacked captioned items."""
    parts = []
    for d, sections in items:
        parts.append(render_sections(sections, with_divider=False, show_captions=True))
    return "\n\n    ".join(parts)


def date_jp(d):
    y, m, day = d.split("-")
    return f"{int(y)}年{int(m)}月{int(day)}日"


# --- templates ---------------------------------------------------------------

DAY_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{date_jp} — daily-proof</title>
  <link rel="stylesheet" href="{lm_roman}" />
  <link rel="stylesheet" href="{lm_sans}" />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700&family=Shippori+Mincho&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="./assets/style.css" />
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [["$", "$"], ["\\\\(", "\\\\)"]],
        displayMath: [["$$", "$$"], ["\\\\[", "\\\\]"]]
      }},
      startup: {{ typeset: false }},
      options: {{ enableMenu: false }}
    }};
  </script>
  <script defer src="{mathjax}"></script>
</head>
<body data-date="{date}">
  <main class="container">
    {content}

    <nav class="calendar-wrap reveal" aria-label="カレンダー">
      <div id="calendar"></div>
    </nav>
  </main>

  <script defer src="./assets/reveal.js"></script>
  <script defer src="./assets/calendar.js"></script>
</body>
</html>
"""

THEME_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{theme} — daily-proof</title>
  <link rel="stylesheet" href="{lm_roman}" />
  <link rel="stylesheet" href="{lm_sans}" />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@500;700&family=Shippori+Mincho&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="./assets/style.css" />
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [["$", "$"], ["\\\\(", "\\\\)"]],
        displayMath: [["$$", "$$"], ["\\\\[", "\\\\]"]]
      }},
      startup: {{ typeset: false }},
      options: {{ enableMenu: false }}
    }};
  </script>
  <script defer src="{mathjax}"></script>
</head>
<body data-theme="{theme}">
  <main class="container">
    <header class="theme-head">
      <h1 class="theme-title">{theme}</h1>
    </header>

    {content}
  </main>

  <script defer src="./assets/reveal.js"></script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>daily-proof</title>
  <style>
    html, body { height: 100%; margin: 0; }
    body { display: grid; place-items: center; background: #fff; color: #9a9a9a;
           font-family: serif; }
  </style>
  <script>
    fetch('./index.json')
      .then(function (r) { return r.json(); })
      .then(function (list) {
        if (!list.length) { document.body.textContent = 'まだ証明がありません。'; return; }
        var pick = list[Math.floor(Math.random() * list.length)];
        location.replace('./' + pick.date + '.html');
      })
      .catch(function () { document.body.textContent = '読み込みに失敗しました。'; });
  </script>
</head>
<body>…</body>
</html>
"""

NEW_TEMPLATE = """tags:

# 命題

# 証明
"""

# Injected into day pages only in `--watch` (preview) mode — never by a plain
# `python3 build.py`, so the committed/CI `docs/` output stays untouched. It
# polls a server-only `./__reload` endpoint (a token that changes on every
# rebuild) and reloads the page when the token moves.
LIVE_RELOAD_SNIPPET = """  <script>
    (function () {
      var seen = null;
      (function poll() {
        fetch('./__reload', { cache: 'no-store' })
          .then(function (r) { return r.text(); })
          .then(function (t) {
            if (seen === null) seen = t;
            else if (t !== seen) location.reload();
          })
          .catch(function () {})
          .then(function () { setTimeout(poll, 700); });
      })();
    })();
  </script>
"""


# --- build -------------------------------------------------------------------

def build(live=False):
    """Regenerate docs/. With live=True, inject the preview live-reload script
    into day pages (used by `--watch`; a plain build never sets this)."""
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ASSETS, OUT / "assets")

    theme_map = json.loads(THEME_MAP.read_text(encoding="utf-8"))
    slugs = {t["name"]: t["slug"] for t in theme_map["themes"]}
    assign = theme_map["assign"]
    # theme name -> list of (date, cluster sections), collected oldest-first
    # (the glob is ascending) so each article reads as it accumulated.
    theme_items = {t["name"]: [] for t in theme_map["themes"]}

    entries = []
    for md in sorted(SRC.glob("*.md")):
        d = md.stem  # YYYY-MM-DD
        text = md.read_text(encoding="utf-8")
        sections = parse(text)
        tags = parse_tags(text)  # stored in index.json only, not rendered
        assign_days_into_themes(d, sections, assign, slugs, theme_items)
        page = DAY_TEMPLATE.format(
            date=d,
            date_jp=date_jp(d),
            content=render_sections(sections, eyebrow_html=date_jp(d), show_captions=True),
            mathjax=MATHJAX_CDN,
            lm_roman=LM_ROMAN_CSS,
            lm_sans=LM_SANS_CSS,
        )
        if live:
            page = page.replace("</body>", LIVE_RELOAD_SNIPPET + "</body>")
        (OUT / f"{d}.html").write_text(page, encoding="utf-8")
        entries.append({"date": d, "tags": tags})

    entries.sort(key=lambda e: e["date"], reverse=True)
    (OUT / "index.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "index.html").write_text(INDEX_TEMPLATE, encoding="utf-8")

    manifest = []
    for t in theme_map["themes"]:
        name, slug = t["name"], t["slug"]
        items = theme_items[name]
        if not items:
            continue  # a declared theme with nothing assigned yet: no page
        page = THEME_TEMPLATE.format(
            theme=name,
            content=render_theme(items),
            mathjax=MATHJAX_CDN,
            lm_roman=LM_ROMAN_CSS,
            lm_sans=LM_SANS_CSS,
        )
        (OUT / f"theme-{slug}.html").write_text(page, encoding="utf-8")
        # dates newest-first in the manifest, mirroring index.json's ordering.
        dates = sorted({d for d, _ in items}, reverse=True)
        manifest.append(
            {"name": name, "slug": slug, "file": f"theme-{slug}.html",
             "count": len(items), "dates": dates}
        )
    (OUT / "themes.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"built {len(entries)} proof(s), {len(manifest)} theme(s) into {OUT}/")


def watch(port=8000):
    """Serve docs/ and rebuild on any change to proofs/, assets/ or build.py.

    A server-only `/__reload` endpoint returns a token that changes on each
    rebuild; the injected live-reload script polls it and reloads the open
    page. Standard-library only. Ctrl-C to stop.
    """
    state = {"token": str(time.time())}

    def rebuild():
        build(live=True)
        state["token"] = str(time.time())

    rebuild()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(OUT), **kwargs)

        def do_GET(self):
            if self.path.split("?", 1)[0].rstrip("/") == "/__reload":
                body = state["token"].encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def log_message(self, *args):
            pass  # keep the watch console to build messages only

    httpd = http.server.ThreadingHTTPServer(("", port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"serving {OUT}/ at http://localhost:{port} — watching for changes")

    def snapshot():
        paths = list(SRC.glob("*.md")) + list(ASSETS.rglob("*")) + [ROOT / "build.py"]
        return {str(p): p.stat().st_mtime for p in paths if p.is_file()}

    prev = snapshot()
    try:
        while True:
            time.sleep(0.4)
            cur = snapshot()
            if cur != prev:
                prev = cur
                try:
                    rebuild()
                    print("rebuilt")
                except Exception as exc:  # keep serving even if a draft is broken
                    print(f"build error: {exc}")
    except KeyboardInterrupt:
        pass


def scaffold_today():
    SRC.mkdir(exist_ok=True)
    today = date.today().isoformat()
    f = SRC / f"{today}.md"
    if f.exists():
        print(f"{f} already exists")
        return
    f.write_text(NEW_TEMPLATE, encoding="utf-8")
    print(f"created {f}")


if __name__ == "__main__":
    if "--new" in sys.argv:
        scaffold_today()
    elif "--watch" in sys.argv:
        watch()
    else:
        build()

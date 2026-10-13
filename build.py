#!/usr/bin/env python3
"""Generate the daily-proof static site into docs/.

Sources live in proofs/YYYY-MM-DD.md. Each becomes docs/YYYY-MM-DD.html where
the proposition and the proof each fade in as one group on scroll. Math is
written as $...$ / $$...$$ and rendered client-side by MathJax, so this script
needs only the standard library.
"""

import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "proofs"
OUT = ROOT / "docs"
ASSETS = ROOT / "assets"

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


def restore_math(html, store):
    for i, raw in enumerate(store):
        html = html.replace(f"\x00M{i}\x00", raw)
    return html


def inline(s):
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def md_to_html(text):
    text, store = protect_math(text)
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
        if re.match(r"^\s*-\s+", line):
            flush_para()
            if items is None:
                items = []
            items.append(inline(re.sub(r"^\s*-\s+", "", line)))
        elif line.strip() == "":
            flush_para()
            flush_list()
        else:
            flush_list()
            para.append(line.strip())
    flush_para()
    flush_list()
    return restore_math("\n".join(out), store)


# --- source parsing ----------------------------------------------------------

def parse(text):
    """Return a list of (proposition, proof) pairs in document order.

    A day file may hold several `# 命題` / `# 証明` sections; they are paired
    up sequentially so one day can carry multiple proofs.
    """
    body = text.strip()
    parts = re.split(r"(?m)^#\s+(命題|証明)\s*$", body)
    rest = iter(parts[1:])  # alternating (name, content)

    pairs = []
    pending_prop = None
    for name, content in zip(rest, rest):
        content = content.strip()
        if name == "命題":
            if pending_prop is not None:
                pairs.append((pending_prop, ""))  # proposition with no proof yet
            pending_prop = content
        else:  # 証明
            pairs.append((pending_prop or "", content))
            pending_prop = None
    if pending_prop is not None:
        pairs.append((pending_prop, ""))
    return pairs


def render_sections(pairs, date_jp_str):
    """Build the stacked proposition/proof <section>s for one day page."""
    multi = len(pairs) > 1
    out = []
    first = [True]

    def eyebrow():
        if first[0]:
            first[0] = False
            return f'<p class="eyebrow">{date_jp_str}</p>\n      '
        return ""

    for i, (prop, proof) in enumerate(pairs, 1):
        plabel = f"命題 {i}" if multi else "命題"
        qlabel = f"証明 {i}" if multi else "証明"
        if prop.strip():
            out.append(
                '<section class="block reveal">\n'
                f"      {eyebrow()}<h2 class=\"label\">{plabel}</h2>\n"
                f'      <div class="body">{md_to_html(prop)}</div>\n'
                "    </section>"
            )
        if proof.strip():
            out.append(
                '<section class="block reveal">\n'
                f"      {eyebrow()}<h2 class=\"label\">{qlabel}</h2>\n"
                f'      <div class="body">{md_to_html(proof)}</div>\n'
                '      <p class="qed">∎</p>\n'
                "    </section>"
            )
    return "\n\n    ".join(out)


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

NEW_TEMPLATE = """# 命題

# 証明
"""


# --- build -------------------------------------------------------------------

def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    shutil.copytree(ASSETS, OUT / "assets")

    entries = []
    for md in sorted(SRC.glob("*.md")):
        d = md.stem  # YYYY-MM-DD
        pairs = parse(md.read_text(encoding="utf-8"))
        html = DAY_TEMPLATE.format(
            date=d,
            date_jp=date_jp(d),
            content=render_sections(pairs, date_jp(d)),
            mathjax=MATHJAX_CDN,
            lm_roman=LM_ROMAN_CSS,
            lm_sans=LM_SANS_CSS,
        )
        (OUT / f"{d}.html").write_text(html, encoding="utf-8")
        entries.append({"date": d})

    entries.sort(key=lambda e: e["date"], reverse=True)
    (OUT / "index.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "index.html").write_text(INDEX_TEMPLATE, encoding="utf-8")
    print(f"built {len(entries)} proof(s) into {OUT}/")


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
    else:
        build()

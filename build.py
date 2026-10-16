#!/usr/bin/env python3
"""Generate the daily-proof static site into docs/.

Sources live in proofs/YYYY-MM-DD.md. Each becomes docs/YYYY-MM-DD.html where
the proposition and the proof each fade in as one group on scroll. Math is
written as $...$ / $$...$$ and rendered client-side by MathJax, so this script
needs only the standard library.
"""

import html
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
    return restore_math("\n".join(out), store)


# --- source parsing ----------------------------------------------------------

# Section headings recognised in a day file, in rough document order of use.
# Any sequence of these may appear; same-kind repeats are auto-numbered.
SECTION_KINDS = ("定義", "公理", "補題", "命題", "定理", "証明", "例", "系", "注意")
SECTION_RE = re.compile(
    r"(?m)^#\s+(" + "|".join(SECTION_KINDS) + r")\s*$"
)


def parse(text):
    """Return a list of (kind, content) sections in document order.

    A day file may hold any sequence of the recognised `# <kind>` headings
    (see SECTION_KINDS) — e.g. 定義 / 命題 / 証明 / 例. Empty sections (a
    heading with no body) are dropped. Repeats of the same kind are numbered
    later at render time.
    """
    body = text.strip()
    parts = SECTION_RE.split(body)
    rest = iter(parts[1:])  # alternating (kind, content)

    sections = []
    for kind, content in zip(rest, rest):
        content = content.strip()
        if content:
            sections.append((kind, content))
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


def render_sections(sections, date_jp_str):
    """Build the stacked <section>s for one day page.

    Each (kind, content) section becomes one fade-in block. A kind that occurs
    more than once in the day is numbered (`命題 1`, `命題 2`, …); a lone kind
    is left unnumbered. 証明 blocks get a trailing ∎.

    Tags are intentionally not rendered — they live in index.json only, for
    sorting/filtering later.
    """
    totals = {}
    for kind, _ in sections:
        totals[kind] = totals.get(kind, 0) + 1

    out = []
    first = [True]
    seen = {}

    def eyebrow():
        if not first[0]:
            return ""
        first[0] = False
        return f'<p class="eyebrow">{date_jp_str}</p>\n      '

    for kind, content in sections:
        if totals[kind] > 1:
            seen[kind] = seen.get(kind, 0) + 1
            label = f"{kind} {seen[kind]}"
        else:
            label = kind
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
    if out:
        idx = out[-1].rindex("</section>")
        out[-1] = (
            out[-1][:idx]
            + '  <hr class="divider" aria-hidden="true" />\n    </section>'
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

NEW_TEMPLATE = """tags:

# 命題

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
        text = md.read_text(encoding="utf-8")
        sections = parse(text)
        tags = parse_tags(text)  # stored in index.json only, not rendered
        html = DAY_TEMPLATE.format(
            date=d,
            date_jp=date_jp(d),
            content=render_sections(sections, date_jp(d)),
            mathjax=MATHJAX_CDN,
            lm_roman=LM_ROMAN_CSS,
            lm_sans=LM_SANS_CSS,
        )
        (OUT / f"{d}.html").write_text(html, encoding="utf-8")
        entries.append({"date": d, "tags": tags})

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

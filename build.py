#!/usr/bin/env python3
"""Generate the daily-proof static site into docs/.

Sources live in proofs/YYYY-MM-DD.md. Each becomes docs/YYYY-MM-DD.html with
a scroll-triggered reveal animation. Math is written as $...$ / $$...$$ and
rendered client-side by KaTeX, so this script needs only the standard library.
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

KATEX_VER = "0.16.11"
KATEX_CDN = f"https://cdn.jsdelivr.net/npm/katex@{KATEX_VER}/dist"


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
    meta = {}
    body = text
    if text.startswith("---"):
        _, fm, body = text.split("---", 2)
        for line in fm.strip().splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    body = body.strip()
    parts = re.split(r"(?m)^#\s+(命題|証明)\s*$", body)
    sections = {}
    rest = iter(parts[1:])
    for name, content in zip(rest, rest):
        sections[name] = content.strip()
    prop = sections.get("命題", "")
    proof = sections.get("証明", parts[0].strip() if not sections else "")
    return meta, prop, proof


def date_jp(d):
    y, m, day = d.split("-")
    return f"{int(y)}年{int(m)}月{int(day)}日"


# --- templates ---------------------------------------------------------------

DAY_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title} — daily-proof</title>
  <link href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@400;600&display=swap" rel="stylesheet" />
  <link rel="stylesheet" href="{katex}/katex.min.css" crossorigin="anonymous" />
  <link rel="stylesheet" href="./assets/style.css" />
</head>
<body data-date="{date}">
  <main class="container">
    <header class="site-header">
      <p class="eyebrow reveal" data-delay="60">{date_jp}</p>
      <h1 class="title reveal" data-delay="120">{title}</h1>
      {source}
      <hr class="divider reveal" data-delay="200" aria-hidden="true" />
    </header>

    <section class="block">
      <h2 class="label reveal">命題</h2>
      <div class="body fragmentize">{prop}</div>
    </section>

    <section class="block">
      <h2 class="label reveal">証明</h2>
      <div class="body fragmentize">{proof}</div>
      <p class="qed reveal">∎</p>
    </section>

    <nav class="calendar-wrap" aria-label="カレンダー">
      <div id="calendar"></div>
    </nav>
  </main>

  <script defer src="{katex}/katex.min.js" crossorigin="anonymous"></script>
  <script defer src="{katex}/contrib/auto-render.min.js" crossorigin="anonymous"></script>
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
  <link href="https://fonts.googleapis.com/css2?family=Shippori+Mincho&display=swap" rel="stylesheet" />
  <style>
    html, body { height: 100%; margin: 0; }
    body { display: grid; place-items: center; background: #fff; color: #9a9a9a;
           font-family: 'Shippori Mincho', serif; }
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

NEW_TEMPLATE = """---
title:
date: {date}
source:
---

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
        meta, prop, proof = parse(md.read_text(encoding="utf-8"))
        title = meta.get("title") or d
        source = meta.get("source", "")
        source_html = (
            f'<p class="source reveal" data-delay="160">出典：{source}</p>'
            if source
            else ""
        )
        html = DAY_TEMPLATE.format(
            title=title,
            date=d,
            date_jp=date_jp(d),
            source=source_html,
            prop=md_to_html(prop),
            proof=md_to_html(proof),
            katex=KATEX_CDN,
        )
        (OUT / f"{d}.html").write_text(html, encoding="utf-8")
        entries.append({"date": d, "title": title, "source": source})

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
    f.write_text(NEW_TEMPLATE.format(date=today), encoding="utf-8")
    print(f"created {f}")


if __name__ == "__main__":
    if "--new" in sys.argv:
        scaffold_today()
    else:
        build()

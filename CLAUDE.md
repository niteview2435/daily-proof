# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A personal "one proof a day" site (`1日1証明`). Each day's proposition(s) and proof(s) are written in Markdown and compiled to a standalone static HTML page. Published at https://niteview2435.github.io/daily-proof/. The daily `git` commits double as the continuity record (the GitHub contribution graph).

## Commands

- `make new` — scaffold today's `proofs/YYYY-MM-DD.md` from a template (no-op if it exists)
- `make build` — regenerate the whole site into `docs/` (`python3 build.py`)
- `make serve` — build, then preview at http://localhost:8000
- `make clean` — remove `docs/`

There are no tests and no linter. The dev shell (via `flake.nix` + direnv, or `nix develop`) only provides `python3` and `make`; `build.py` is pure standard library, so plain `python3 build.py` works without the shell.

## Deploy model (important)

Pages source is **GitHub Actions**, not a branch folder. On push to `main`, `.github/workflows/pages.yml` runs `python3 build.py` and deploys `docs/`.

- **A commit alone changes nothing live — you must `push`.** Push triggers build + deploy automatically.
- `docs/` is **git-ignored and not committed**; CI regenerates it. Do not re-add it to tracking.
- Local `make build` is only for previewing; never commit the output.

## Architecture

Single-file generator `build.py` (stdlib only). Math is rendered **client-side by MathJax** — the build never shells out to a TeX engine.

Source → one file per day: `proofs/YYYY-MM-DD.md`. The date comes from the filename (no frontmatter). A file may contain:
- an optional leading `tags:` line (comma / 、 / space separated) before the first heading, and
- one or more `# <kind>` sections in any order, where `<kind>` is one of the recognised headings (`build.py`'s `SECTION_KINDS`: 定義 / 公理 / 補題 / 命題 / 定理 / 証明 / 例 / 系 / 注意). A heading may carry an optional one-line **caption** after the kind (`# 命題 相対位相の閉集合の特徴づけ`) — authored in the Markdown and shown on both day and theme pages (in parentheses, body serif, beside the label). Any kind that repeats on a day is auto-numbered (`命題 1 / 命題 2 / …`), independently per kind; a lone kind is left unnumbered. An empty section (heading with no body) is dropped.

`build.py` pipeline:
- `parse()` → list of `(kind, caption, content)` sections in document order; `parse_tags()` → tag list.
- `md_to_html()` is a deliberately tiny Markdown subset (paragraphs, `-` lists, `**bold**`/`*italic*`/`` `code` ``). Consecutive non-blank lines join into one paragraph; blank lines separate paragraphs. A rule line (`---`/`***`/`___`) is treated as a block separator only — no `<hr>` is emitted, so stray separators in pasted drafts stay harmless.
- Math safety: `protect_math()`/`restore_math()` swap `$...$` and `$$...$$` spans for placeholders **around** the Markdown pass so Markdown can't mangle them, then restore the raw TeX for MathJax.
- `render_sections(sections, eyebrow_html, with_divider, show_captions)` emits stacked `<section class="block reveal">` groups (one per section; 証明 blocks get a trailing ∎); `eyebrow_html` (the date, on day pages) is placed above the first block, the divider `<hr>` rides inside the **last** section when `with_divider` is set, and `show_captions` (set on both day and theme pages) renders each heading's caption as a `<span class="caption">` beside its label. Tags are deliberately **not** rendered — they are written only into `index.json` for future sorting/filtering.
- Theme articles (分野記事): `split_clusters()` breaks a day into **items** (each 定義/公理/補題/命題/定理/系 opens a new item; a following 証明/例/注意 attaches to the item above). `theme_map.json` maps each day to a theme (or, when a day spans themes, one theme name per item in document order); `assign_days_into_themes()` files every item under its theme and `render_theme()` stacks a theme's items oldest-first — captioned by their headings, with **no** source-day eyebrow and **no** dividers. This is a read-later **reorganisation layer over the daily log** — the daily pages remain the primary artifact.
- `DAY_TEMPLATE` / `THEME_TEMPLATE` / `INDEX_TEMPLATE` are `str.format` templates. Literal braces in a template must be doubled (`{{ }}`) — see the MathJax config block. Substituted values may safely contain `{ }` (e.g. `\frac{}{}`).

`theme_map.json` (repo root, **hand-maintained by Claude — the author never touches it**): `{themes: [{name, slug}], assign: {YYYY-MM-DD: name | [name, …]}}`. Themes are kept **broad** (a few standing fields like 高校数学 / 確率論 / 位相空間論); new proofs accrete into existing themes rather than spawning a narrow new one, unless a genuinely new field appears. **Workflow when a new `proofs/` day is added:** read it, then add an `assign` entry — a single theme name if the whole day is one field, or a per-item list if it splits across fields (count must equal the day's item count, or be a single name to broadcast). Use an existing theme when it fits; add to `themes[]` only for a real new field. An unassigned day just prints a build warning and is omitted from articles (the daily page is unaffected); an unknown theme name or a list-length mismatch is a hard build error.

Output in `docs/`:
- `YYYY-MM-DD.html` per day.
- `theme-<slug>.html` per theme that has ≥1 item.
- `index.json` — manifest `[{date, tags}]`, newest first.
- `themes.json` — manifest `[{name, slug, file, count, dates}]` in `theme_map.json` order (for a future portfolio entry point to fetch, mirroring `index.json`).
- `index.html` — there is **no dedicated home**; it fetches `index.json`, picks a random date, and `location.replace()`s to that day page.
- `assets/` — copied verbatim from the top-level `assets/`.

`assets/` (edit these directly; the build copies them):
- `reveal.js` — IntersectionObserver that adds `.in-view` to `.reveal` elements (fade + blur + translateY, the "Web5" reveal). MathJax auto-typeset is disabled in the page config and triggered here after the DOM is ready.
- `calendar.js` — builds the month grid from `index.json`: proof days get strong text and link to their page, the open day is a filled circle, arrows change month. Defaults to the page's own month.
- `style.css` — monochrome design driven by `--ink` CSS vars; Latin Modern (Roman body, Sans headings) with Shippori Mincho / Noto Sans JP fallbacks for Japanese.

All asset/data references use relative `./` paths so the site works under the `/daily-proof/` Pages subpath.

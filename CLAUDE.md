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
- one or more `# 命題` / `# 証明` section pairs. Multiple pairs on one day are supported and auto-numbered (`命題 1 / 証明 1 / …`).

`build.py` pipeline:
- `parse()` → list of `(proposition, proof)` pairs in document order; `parse_tags()` → tag list.
- `md_to_html()` is a deliberately tiny Markdown subset (paragraphs, `-` lists, `**bold**`/`*italic*`/`` `code` ``). Consecutive non-blank lines join into one paragraph; blank lines separate paragraphs.
- Math safety: `protect_math()`/`restore_math()` swap `$...$` and `$$...$$` spans for placeholders **around** the Markdown pass so Markdown can't mangle them, then restore the raw TeX for MathJax.
- `render_sections()` emits stacked `<section class="block reveal">` groups; the date + tags appear once at the top, the divider `<hr>` rides inside the **last** section (so it fades in with the final proof).
- `DAY_TEMPLATE` / `INDEX_TEMPLATE` are `str.format` templates. Literal braces in a template must be doubled (`{{ }}`) — see the MathJax config block. Substituted values may safely contain `{ }` (e.g. `\frac{}{}`).

Output in `docs/`:
- `YYYY-MM-DD.html` per day.
- `index.json` — manifest `[{date, tags}]`, newest first.
- `index.html` — there is **no dedicated home**; it fetches `index.json`, picks a random date, and `location.replace()`s to that day page.
- `assets/` — copied verbatim from the top-level `assets/`.

`assets/` (edit these directly; the build copies them):
- `reveal.js` — IntersectionObserver that adds `.in-view` to `.reveal` elements (fade + blur + translateY, the "Web5" reveal). MathJax auto-typeset is disabled in the page config and triggered here after the DOM is ready.
- `calendar.js` — builds the month grid from `index.json`: proof days get strong text and link to their page, the open day is a filled circle, arrows change month. Defaults to the page's own month.
- `style.css` — monochrome design driven by `--ink` CSS vars; Latin Modern (Roman body, Sans headings) with Shippori Mincho / Noto Sans JP fallbacks for Japanese.

All asset/data references use relative `./` paths so the site works under the `/daily-proof/` Pages subpath.

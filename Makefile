.PHONY: build serve preview new clean

# Newest proof's output page, e.g. 2026-10-13.html (empty if no proofs yet).
LATEST := $(notdir $(lastword $(sort $(wildcard proofs/*.md))))
LATEST_HTML := $(LATEST:.md=.html)

# Generate the static site into docs/ for local preview only.
# docs/ is git-ignored; on push, GitHub Actions rebuilds and deploys it.
build:
	python3 build.py

# Build, then preview locally (plain server; open any page yourself).
serve: build
	python3 -m http.server 8000 --directory docs

# Build, serve, and auto-open the newest proof in the browser.
preview: build
	@( sleep 1; open "http://localhost:8000/$(LATEST_HTML)" ) &
	python3 -m http.server 8000 --directory docs

# Scaffold today's proof file in proofs/ (no-op if it already exists).
new:
	python3 build.py --new

clean:
	rm -rf docs

.PHONY: build serve new clean

# Generate the static site into docs/ (committed; GitHub Pages serves /docs).
build:
	python3 build.py

# Build, then preview locally.
serve: build
	python3 -m http.server 8000 --directory docs

# Scaffold today's proof file in proofs/ (no-op if it already exists).
new:
	python3 build.py --new

clean:
	rm -rf docs

# Contributing

This is a small tool maintained by the [SMC Lab](https://smcclab.github.io) for
our own curriculum work, but bug reports and patches are welcome — especially
when ANU changes a page and a parser stops working.

## Setting up

```bash
git clone https://github.com/smcclab/anu-pandc.git
cd anu-pandc
uv sync
uv run pytest
```

The tests run entirely against saved HTML in `tests/fixtures/`, so they need no
network and take a couple of seconds.

## When a page stops parsing

P&C changes without notice, and a parser failure is the most likely bug you
will hit. The fix has a standard shape:

1. Save the page that broke:
   `uv run anu-pandc get COMP1730 --year 2026 -v` shows the URL it fetched.
2. Add the raw HTML to `tests/fixtures/`, trimmed to the part that matters if
   it is large.
3. Write a failing test in the matching `tests/test_parse_*.py`.
4. Fix the parser in `src/anu_pandc/parse/`.

Please keep fixtures small and don't add pages containing anything that isn't
already public on the P&C website.

## House rules

- Be polite to the server. The default half-second rate limit and the
  identifying User-Agent in `src/anu_pandc/http.py` stay as they are; nothing
  should bypass `http.get()`.
- The parsers take a BeautifulSoup tree and return plain dicts. Keep rendering
  (`render.py`) and storage (`store.py`) separate from parsing, so saved HTML
  can be re-parsed offline.
- New CLI output goes to stdout; progress and warnings go to stderr, so piping
  stays safe.
- Add a line to `CHANGELOG.md` under "Unreleased".

## Releasing

1. Update `version` in `pyproject.toml` and `__version__` in
   `src/anu_pandc/__init__.py` — they must match.
2. Move the `CHANGELOG.md` entries from "Unreleased" into the new version.
3. `uv build && uvx twine check dist/*`.
4. Tag `vX.Y.Z` and push the tag.

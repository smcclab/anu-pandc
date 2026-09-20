# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `AGENTS.md` at the repository root, where an agent looks before it reads
  anything else. It splits on whether there is a shell: `uvx` one-liners if
  there is, the raw URLs of the three `docs/` files if there is not, and in
  both cases a table of which source answers which kind of question.

### Fixed

- The README led a model that cannot run the CLI to a 404. Its links to
  `docs/` were relative, so an agent handed the repository URL and reading the
  raw Markdown built `github.com/smcclab/anu-pandc/docs/…` — which does not
  exist — rather than the `blob/main` path a rendered link resolves to. Those
  links are absolute now.

- The README also buried the answer for such a model. Everything above
  "Further reading" is a command line it cannot use, and the two documents
  written for it were named on the second-to-last line of a 343-line file. A
  section near the top now sends it straight to them, and says that a question
  with a date in it is a calendar question before it is a timetable one.

## [0.3.0] — 2026-09-20

### Added

- Four more ANU sources, on the grounds that a coursework question rarely
  stays inside Programs & Courses. What a course must do is in legislation,
  how the University applies that is in the Policy Library, when it happens is
  in the university calendar, and where the class meets is in the timetable.

  - `policy get|search|list` — the ANU Policy Library. A document comes back
    with its body as Markdown and the governance metadata that decides whether
    it still binds anyone: effective and next-review dates, responsible
    officer, approving body, and the legislation it is made under. Clause
    numbering is preserved, because a policy cites its own clauses and the
    numbers live in `<ol start=...>` rather than in the text.
  - `legislation list|get|search` — University legislation, from ANU's index
    of what applies and the Federal Register of Legislation for status and
    text. Fetching an instrument is two requests: the Register's `/latest/text`
    URL is a JavaScript shell, and the document is in the EPUB at a URL built
    from the version's start date.
  - `timetable TERM... --year Y` — scheduled classes from the Allocate+ Web
    Publisher, with contact hours for one student counted one stream per
    activity group rather than all the alternatives.
  - `calendar --year Y` — census dates, teaching breaks, exam periods, results
    and public holidays from the university calendar feed, with `--ranges` to
    pair the begins/ends events back into ranges.

- `docs/reading-anu-sources-directly.md`, the companion to
  `reading-pandc-directly.md` for those four sources: which one answers which
  kind of question, the URL shapes, and the quirks that make each easy to read
  wrongly.

- `anu_pandc.parse.html_md`, a small HTML-to-Markdown converter for the prose
  documents the new sources serve, where the structure is the content rather
  than a set of named fields.

### Changed

- `http` is no longer specific to Programs & Courses. A 403 names the host it
  was actually refused for, `post` and `fetch_json` join `get` and
  `fetch_page` on the same session and rate limit, and `HOSTS` lists every site
  the tool reads for anyone writing an egress allow-list.

- `fetch_page` hands the response bytes to BeautifulSoup when the server
  declares no charset, so the document's own declaration is used. The Federal
  Register serves its text that way, and the previous ISO-8859-1 fallback
  turned every em dash in an instrument into mojibake.

- A saved tree gained `<year>/timetable-<TERM>.*` and `<year>/calendar.*`, plus
  `policy/` and `legislation/` directories above the year directories for the
  documents that have no year.

## [0.2.0] — 2026-09-17

### Added

- Special-topics classes carry their advertised topic. P&C names the topic
  of each instance of a topics shell (COMP2710, COMP3710, COMP4011, ...) in a
  wide row above the class row on the course page's class tab; it is now
  `offering["topic"]`, rendered after the class number in the `Offered in`
  line ("... class 9011) — Software Verification using Proof Assistant"),
  recovered by `course_from_markdown`, and a `topic` column in the
  `offerings` CSV/Markdown output.

### Fixed

- Prerequisites are read from the whole "Requisite and Incompatibility"
  section rather than `div.requisite` alone, and the prerequisite/
  incompatibility split keys off the incompatibility markers instead of a
  literal "To enrol in this course you must" lead-in. The old parser returned
  None for the comma variant, the shorter "To enrol you must", bare conditions
  with no lead-in ("12 units of 3000 and/or 4000 level COMP courses."), and
  the four courses with no `div.requisite` at all (COMP3710, COMP5920,
  COMP6470, COMP8820).

## [0.1.1] — 2026-09-17

### Added

- A 403 now explains itself: the error says whether the refusal carried
  Programs & Courses' own headers (ANU refused it), or an `x-deny-reason`
  header (your own egress gateway refused the host outright), or neither (a
  proxy or firewall in between), and what to do about each. The README gains a
  section on running the tool from sandboxes, CI and agent environments.
- `ANU_PANDC_USER_AGENT` overrides the default identifying User-Agent.

## [0.1.0] — 2026-09-17

First tagged release. Split out of the ANU School of Computing curriculum
analysis repository into a standalone package.

### Added

- `get` — fetch programs, subplans and courses by code, as Markdown or JSON,
  with `--recursive` to walk a program down to every course it names.
- `courses` — bulk-fetch every code in a saved tree's `course-codes.txt`.
- `catalogue` — list every course under a subject prefix from the P&C search
  API, as Markdown, CSV or JSON.
- `classes` — class summary pages: convener, dates, and the real assessment
  schedule.
- `offerings` — planned sittings per course, split by offering year, including
  future years that have no catalogue yet.
- `conveners` — convener and lecturer per saved class, with name aliasing.
- `url` — print P&C URLs for a list of codes.
- A saved-tree layout (`DIR/<year>/…`) designed to be grepped, diffed and
  committed, with `--force` to re-fetch and a `scrape-log.md` audit trail.

[Unreleased]: https://github.com/smcclab/anu-pandc/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.3.0
[0.2.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.2.0
[0.1.1]: https://github.com/smcclab/anu-pandc/releases/tag/v0.1.1
[0.1.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.1.0

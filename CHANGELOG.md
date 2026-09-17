# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/smcclab/anu-pandc/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.2.0
[0.1.1]: https://github.com/smcclab/anu-pandc/releases/tag/v0.1.1
[0.1.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.1.0

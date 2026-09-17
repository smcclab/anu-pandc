# Changelog

All notable changes to this project are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A 403 now explains itself: the error says whether the refusal carried
  Programs & Courses' own headers (ANU refused it) or none of them (a proxy,
  firewall or sandbox egress allow-list in between did), and what to do about
  each. README gains a section on running the tool from sandboxes, CI and
  agent environments.
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

[Unreleased]: https://github.com/smcclab/anu-pandc/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/smcclab/anu-pandc/releases/tag/v0.1.0

# anu-pandc

A command-line interface to [ANU Programs & Courses](https://programsandcourses.anu.edu.au).

> **Unofficial.** This is a personal project. It is not affiliated with,
> endorsed by, or supported by the Australian National University. It reads the
> public Programs & Courses website; it holds no data of its own.

Point it at any program, major/minor/specialisation or course code and a year.
It prints the page as clean Markdown (or JSON), or saves a whole year of a
school's curriculum as a tree of small files you can grep, diff and commit.

It also fetches per-class summary pages (convener, dates, real assessment
schedule), lists every course under a subject prefix from the catalogue search
API, and extracts planned offerings for future years before P&C publishes them.

## Install

With [uv](https://docs.astral.sh/uv/):

```bash
uv tool install anu-pandc
anu-pandc --help
```

Or run it without installing:

```bash
uvx anu-pandc get COMP1730 --year 2026
```

Or with pip: `pip install anu-pandc`. Python 3.11 or newer.

To track the development version instead, install from the repository:
`uv tool install git+https://gitlab.anu.edu.au/u4110680/anu-pandc.git`.

## Status

Best effort. It reads pages ANU changes without notice, so a P&C redesign will
break it until the parsers are updated. It is polite by default: one session, a
self-identifying User-Agent, and a half-second pause before every request. Turn
that up with `--rate` when reading a lot at once, and please don't turn it down
to zero against the live site.

## Quick start

```bash
# Look at one thing. The code's shape says what it is.
anu-pandc get COMP1730 --year 2026            # a course
anu-pandc get BCOMP --year 2026               # a program
anu-pandc get ARTIF-SPEC --year 2026          # a specialisation (also *-MAJ, *-MIN)
anu-pandc get 7706XMCOMP --year 2026 --json   # structured output instead of Markdown

# Save a program and everything under it: its majors/minors/specialisations,
# then every course any of them names.
anu-pandc get BCOMP HCOMP --year 2026 --save ./data --recursive

# Every COMP course in the 2026 catalogue, including ones no program names.
anu-pandc catalogue COMP --year 2026 --save ./data

# Now fetch any courses the catalogue found that --recursive didn't.
anu-pandc courses --year 2026 --save ./data

# Class summaries (convener, census date, assessment with due dates).
anu-pandc classes COMP1100 --year 2026
anu-pandc classes --year 2026 --save ./data --prefix COMP   # every saved COMP course

# Which sessions each course runs in, for this year and the future years
# already loaded on the course pages.
anu-pandc offerings --year 2027 --from ./data --prefix COMP --save ./data

# Who convened what, from the saved class pages.
anu-pandc conveners --from ./data --prefix COMP -o conveners.csv
```

Markdown is rendered nicely when printing to a terminal; pipe it or pass
`--plain` to get the raw text. Progress goes to stderr so stdout is safe to
redirect.

## Commands

| Command | What it does |
|---------|--------------|
| `get CODE... --year Y` | Fetch programs, subplans or courses. `--save DIR` writes files; `--recursive` walks program → subplans → courses. `--kind` overrides the auto-detected type. |
| `courses --year Y --save DIR` | Bulk-fetch every code in `DIR/Y/course-codes.txt` (or the codes given). `--prefix COMP` to restrict. |
| `classes [CODE...] --year Y` | Fetch class summary pages. All periods by default; `--period "First Semester"` to narrow. With no code and `--save`, uses the saved code list. |
| `catalogue PREFIX --year Y` | Every course under a subject prefix via the search API. `-f md/csv/json`. Saving also adds the teaching codes to `course-codes.txt` (`--include-research` to add HDR shells too). |
| `offerings --year Y` | Planned sittings per course, split by offering year. Reads saved pages with `--from DIR` or fetches the codes given. `-f csv/md/json`. |
| `conveners --from DIR` | Convener and lecturer per saved class. `--aliases FILE` to merge name variants. |
| `url CODE... --year Y` | Just print the P&C URLs. |

Global options: `--rate SECONDS` (pause between requests, default 0.5),
`-v` to log every fetch, `-q` for errors only.

## Output tree

`--save DIR` produces:

```
DIR/2026/
  programs/BCOMP.md            one file per program
  subplans/COMS-MAJ.md         majors, minors, specialisations
  courses/COMP1100.md          one file per course
  classes/COMP1100-FirstSemester-3695.md
  catalogue-COMP.md            all COMP courses that year (code, title, career, units, sessions)
  offerings-COMP.csv           planned sittings for the 2026 offering year
  course-codes.txt             union of every course code seen so far
  scrape-log.md                append-only record of what was fetched when
```

Pass `-f json` (or both `-f md -f json`) to `get`, `courses` and `classes` to
write `.json` files with the same names. Existing files are skipped unless
`--force` is given, so re-running a bulk command only fetches what is missing.

## What gets parsed

**Course pages**: title, units, level, prerequisites and incompatibilities
(split heuristically, with the raw requisite text preserved), co-taught
codes, description, learning outcomes, indicative assessment with weights, and
the "Offered in" table (year, session, mode, class number, summary link).

**Program and subplan pages**: title, total units, introduction, learning
outcomes, requirement groups as tables of courses, and the list of
majors/minors/specialisations offered.

**Class summary pages**: convener and lecturer, mode, start/end/census/last-
enrol dates, description, learning outcomes, assessment summary table with due
dates and LO mapping, per-task detail, examinations, participation, late-
submission and extension policies, class schedule, resources, and tutorial
registration.

## Notes on P&C behaviour

- A course page carries class rows for every future year the schedule has been
  loaded for, not just its own year. That is why `offerings` produces one table
  per offering year and can show a year that has no catalogue yet.
- Program pages for a future year are often published before its subplan or
  course pages exist.
- Unknown codes return HTTP 200 with a "page doesn't exist" body. The tool
  detects that and reports an error rather than saving it.
- Requests are rate-limited (0.5 s apart) and sent with an identifying
  User-Agent. Please keep it that way.

## Using it as a library

```python
from anu_pandc.scrape import fetch_item
course = fetch_item("COMP1730", "2026")
course.data["learning_outcomes"]
course.markdown()
```

The parsers in `anu_pandc.parse` take a BeautifulSoup tree and return plain
dicts, so they can be run over saved HTML too.

## Development

```bash
git clone https://gitlab.anu.edu.au/u4110680/anu-pandc.git
cd anu-pandc
uv sync
uv run pytest
```

Tests run against saved HTML fixtures in `tests/fixtures/`; no network needed.

## Licence

MIT. Written by Charles Martin for curriculum work in the ANU School of
Computing; not an official ANU tool.

# AGENTS.md

`anu-pandc` reads [ANU Programs & Courses](https://programsandcourses.anu.edu.au)
and the four other ANU sources a curriculum question runs into: the Policy
Library, University legislation, the class timetable and the university
calendar. Unofficial; a tool from the SMCC Lab in the ANU School of Computing.

## If you can run a shell

Use the CLI. It needs no checkout:

```bash
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc get COMP1100 --year 2026
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc classes COMP1100 --year 2026
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc timetable COMP1100 --year 2026 --week 2026-09-21
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc calendar --year 2026 --ranges
```

`--help` lists the rest. Read
[README.md](https://github.com/smcclab/anu-pandc/blob/main/README.md) for the
full command set, and its "Running it elsewhere" section if a fetch returns 403
— in a sandbox with an egress allow-list that is almost always your own gateway
refusing `programsandcourses.anu.edu.au`, not ANU.

## If you cannot run a shell

Do not try to install anything, and do not guess URLs. Fetch these two files
and follow them — they are written for you, and they carry the URL shapes, the
parsing traps and the etiquette:

- **Programs & Courses** — courses, programs, majors/minors/specialisations,
  class summaries, who is convening something, and how to work out which year
  and teaching period a question is actually about:
  <https://raw.githubusercontent.com/smcclab/anu-pandc/main/docs/reading-pandc-directly.md>
- **The other four sources** — the Policy Library, University legislation,
  MyTimetable and the university calendar:
  <https://raw.githubusercontent.com/smcclab/anu-pandc/main/docs/reading-anu-sources-directly.md>
- **The P&C JSON API** — the undocumented catalogue-search endpoints:
  <https://raw.githubusercontent.com/smcclab/anu-pandc/main/docs/pc-api.md>

## Which source answers which question

Getting this wrong is the commonest way to answer confidently and wrongly.

| The question | The source |
|--------------|-----------|
| What is this course? What does it require? Who convenes it? | P&C course page, then the class summary |
| What is the *real* assessment schedule, with due dates? | the class summary, not the course page's "indicative assessment" |
| When and where does the class meet? | MyTimetable — scheduled, not evidence of delivery |
| What is on in one particular week? | MyTimetable with `--week YYYY-MM-DD`; a whole-year timetable is a weekly *pattern* across every teaching period and cannot answer it |
| What week is it? Census, teaching breaks, exams, results? | the university calendar |
| How does the University apply a rule? | the Policy Library |
| What *must* happen, and who may decide it? | legislation — Statutes, Rules, Orders |

Legislation beats policy, policy beats procedure, and a class summary beats all
of them for what a particular class actually did.

## Two traps worth knowing before you fetch anything

- **Resolve the year and teaching period explicitly.** Course pages are
  year-scoped and the year the user means is often not the current one. A
  question with a date in it is a **calendar** question first — settle the date
  against the calendar, then go to the timetable or the class summary.
- **An unknown code returns HTTP 200** with a "page doesn't exist" body. A 200
  is not proof the thing exists; check the body.
- **The timetable knows about teaching breaks.** If scheduled classes turn up
  inside a break you worked out from the calendar, your range is wrong, not the
  timetable — a "Return from ..." date is the first day back, not the last day
  off. Never tell anyone a scheduled class will not run on the strength of a
  date range you paired yourself.

## Working on this repository

`uv sync`, then `uv run pytest`. Tests run against saved HTML fixtures in
`tests/fixtures/`, so no network is needed. See
[CONTRIBUTING.md](https://github.com/smcclab/anu-pandc/blob/main/CONTRIBUTING.md)
for how to fix a parser when ANU changes a page.

## Etiquette

One session, an identifying User-Agent, half a second between requests. Turn
that up with `--rate` when reading a lot at once; please don't turn it down
against the live site. If you are hand-fetching, pause between requests too.

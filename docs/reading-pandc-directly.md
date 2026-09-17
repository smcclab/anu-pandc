# Reading Programs & Courses directly

**This is a fallback. If you can run `anu-pandc`, stop reading and run it.**

It exists for one situation: an assistant that has a web-fetch or browser tool
but cannot run this CLI — a chat session, a cloud agent, a sandbox whose egress
allow-list refuses `programsandcourses.anu.edu.au` to the tool while permitting
it to the browser integration. Everything below is a plain HTTPS GET against
the public site.

Hand-fetching is strictly worse than the CLI where the CLI works. You re-derive
parsers that already exist and get no rate limiting, no saved tree, no
not-found detection, and no `offerings`/`conveners` aggregation. On a machine
with a checkout or `uvx`, the CLI is the right answer even for a single lookup:

```bash
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc get COMP1730 --year 2026
```

So: try the CLI first, and only fall back here once a fetch has actually been
refused. The other use for this document is as the reference for what the CLI
is doing under the hood.

The URLs and quirks here were checked against the live site on 2026-09-17.

## 1. The five things you can fetch

| What | URL | Gives you |
|------|-----|-----------|
| Course | `/{year}/course/{CODE}` | Description, learning outcomes, indicative assessment, prerequisites, incompatibilities, units, co-taught pair, **and the offerings table for that year and the next two** |
| Program | `/{year}/program/{CODE}` | Requirements, unit counts, the course lists, links to its majors/minors/specialisations |
| Major / minor / specialisation | `/{year}/major/{CODE}`, `/{year}/minor/{CODE}`, `/{year}/specialisation/{CODE}` | Requirement lists for that subplan |
| Class summary | `/{year}/course/{CODE}/{Period}/{ClassNumber}` | **Course convener and lecturer**, real assessment items with weights and due dates, class dates, mode |
| Catalogue search | `/data/...` JSON endpoints — see §4 | Every course/major/minor/spec/program for a year, as JSON |

Base: `https://programsandcourses.anu.edu.au`.

### Picking the right URL from a code

The code's *shape* tells you which of the three page types it is:

- `^[A-Z]{2,4}\d{4}[A-Z]?$` → **course**. `COMP1100`, `MATH1005`, `COMP8900F`.
- ends in `-MAJ` / `-MIN` / `-SPEC` / `-HSPC` / `-SPC` → **subplan**.
  `-MAJ` → `/major/`, `-MIN` → `/minor/`, everything else → `/specialisation/`.
  `COMS-MAJ`, `HCCC-MIN`, `ARTIF-SPEC`, `MLCV-HSPC`.
- anything else → **program**. `BCOMP`, `MMLCV`, `7706XMCOMP`.

Codes are upper-case. The year is always the first path segment, and it is
never optional — there is no "current year" URL.

Examples:

```
https://programsandcourses.anu.edu.au/2026/course/COMP1100
https://programsandcourses.anu.edu.au/2026/program/BCOMP
https://programsandcourses.anu.edu.au/2026/specialisation/ARTIF-SPEC
https://programsandcourses.anu.edu.au/2026/course/COMP1100/First%20Semester/3695
```

### Knowing when a page doesn't exist

A bad code does **not** 404. It answers `302` to `/Error/Index/404?aspxerrorpath=...`,
and a fetch tool that follows redirects will hand you a 200 with `<title>Error</title>`
or a "page you are looking for doesn't exist" body. Check the title before you
believe anything on the page. An empty-looking course page is usually a wrong
code or a year in which the course didn't exist, not a course with no content.

## 2. Who is teaching a course

The convener is published **only on class summary pages**, not on the course
page. Two fetches:

1. `GET /{year}/course/{CODE}` and find the `#class` tab ("Offerings, Dates and
   Class Summary Links"). Each row is one class: class number, start date, last
   day to enrol, census date, end date, mode, and a Class Summary link.
2. Follow the Class Summary link. It looks like
   `/{year}/course/{CODE}/{Period}/{ClassNumber}` with the period URL-encoded
   (`First%20Semester`). Read "Course Convener" and "Lecturer" from the summary
   block near the top.

Do not hand-build the class URL from a guessed class number — take the href
from the course page. Class numbers are per-year and not derivable.

**The link is `N/A` for future years.** P&C publishes planned offerings with
dates and class numbers a year or two ahead, but no class summary, so the
convener for a future year is simply not published. If you are asked who is
teaching something next year, say that P&C doesn't carry it rather than
reporting last year's convener as current.

Caveats when you do get a name:

- A class summary can list several conveners. That is genuine co-convening
  *or* convener-plus-guest, and the page does not distinguish them. Don't
  divide a name list into fractional teaching loads without checking.
- Names carry honorifics inconsistently (`Prof Dirk Pattinson`,
  `Dr Dirk Pattinson`, `Dirk Pattinson`) and some people appear under more
  than one spelling across years. Match on surname, not the full string.
- A course offered in both semesters has two class summaries, often with
  different conveners. Always say which semester you looked at.

## 3. Is it offered, and when

The `#class` tab on the course page is the authoritative answer, and it spans
**three years**: fetching `/2026/course/COMP1100` gives you the 2026, 2027 and
2028 offering tables in one page. So you can read a teaching plan for a year
whose catalogue does not exist yet.

A course page with no rows in the class tab is not offered that year.

Don't use the catalogue API's `Session` field for this — see the quirks below.

## 4. The JSON API

The catalogue page is backed by JSON endpoints under `/data/`. Use these when
you want a *list* (every COMP course, every specialisation); use the HTML pages
when you want the detail of one thing.

All take `SearchText`, `PageIndex`, `MaxPageSize`, `SelectedYear`.

| Endpoint | Returns |
|----------|---------|
| `/data/CourseSearch/GetCourses` (add `AppliedFilter=FilterByCourses`) | `CourseCode`, `Name`, `Session`, `Career`, `Units`, `ModeOfDelivery`, `Year` |
| `/data/MajorSearch/GetMajors` | `SubPlanCode`, name, units, career |
| `/data/MinorSearch/GetMinors` | same shape |
| `/data/SpecialisationSearch/GetSpecialisations` | same shape, plus `SubplanType` |
| `/data/ProgramSearch/GetProgramsUnderGraduate` | `AcademicPlanCode`, name, ATAR, duration, `CanCombine`, mode. Also `...PostGraduate`, `...Research`, `...NonAward` |

```
https://programsandcourses.anu.edu.au/data/CourseSearch/GetCourses?AppliedFilter=FilterByCourses&SearchText=COMP&PageIndex=0&MaxPageSize=50&SelectedYear=2026
```

Quirks, all still true as of the date at the top:

- **Page size is capped at 10** no matter what `MaxPageSize` says. Paginate
  `PageIndex=0,1,2,…` until you have `TotalCount` items. COMP in 2026 is 194
  courses — twenty requests.
- **`SearchText` matches titles as well as codes.** Searching `COMP` returns
  courses with "comp" in the name. Filter on `CourseCode.startswith(prefix)`.
- **Most server-side filters are ignored** (`Semesters=`, the
  `FilterByMajors/Minors/Specialisations` values). `Careers=Undergraduate` on
  `GetCourses` does work. Safest to fetch broadly and filter yourself.
- **`Session` is not a teaching plan.** `""` means not offered that year.
  `"First Semester/Second Semester"` means both. The full
  `"Summer Session/First Semester/Autumn Session/Winter Session/Second Semester/Spring Session"`
  and the `Quarter 1/…/Quarter 4` string are HDR research shells (`Career`
  is `Research`, codes like `COMP8900F`) — they mean "enrol any time", not
  "taught six times". For a real answer, read the course page's class tab.
- **Historical years work**, back to at least 2015.
- A zero-result query returns a `Suggestion` field (spelling correction).

## 5. Working out *when* you are

Course pages are year-scoped, so every question needs a year, and the year the
user means is often not the current one. Resolve it explicitly before fetching.

Start from today's date, then:

- **Which year's catalogue is live.** P&C publishes the next year well before
  it starts; both are fetchable all year. "This year" = the calendar year of
  today's date.
- **Which teaching period is running.** ANU's main periods, with the 2026
  dates as published on class pages:

  | Period | URL form | 2026 dates |
  |--------|----------|------------|
  | First Semester | `First%20Semester` | 23 Feb – 29 May (census 31 Mar) |
  | Second Semester | `Second%20Semester` | 27 Jul – 30 Oct (census 31 Aug) |
  | Summer Session | `Summer%20Session` | Nov–Feb |
  | Autumn Session | `Autumn%20Session` | Mar–Jun |
  | Winter Session | `Winter%20Session` | Jun–Aug |
  | Spring Session | `Spring%20Session` | Sep–Nov |

  Dates shift by a week or so each year. To get them exactly for year Y, open
  any course page for Y and read the class tab — every row carries start, last
  day to enrol, census and end dates, including for future years.

- **Then map the question onto a year.** The traps:
  - "Who teaches COMP1100?" in September 2026 means the S2 2026 class if it
    runs in S2, otherwise the most recent S1. Say which you answered.
  - "What's running next semester?" in September 2026 means **S1 2027** — a
    different catalogue year, and one with no conveners published.
  - "Is X still offered?" needs the *next* year's page, not this one. A course
    can be in the 2026 catalogue and absent from 2027.
  - Anything about assessment weights or due dates needs a class summary for a
    specific year and period; the course page's "Indicative Assessment" is
    deliberately indicative and often out of date relative to the class.

  When a question is ambiguous between two years, fetch both and say what
  changed. It is two requests.

## 6. What you cannot get this way

- **Conveners for future years** — not published (§2).
- **Enrolment numbers, SELT scores, teaching allocations** — none of this is on
  P&C at all. It comes from internal ANU exports.
- **Timetables** — P&C links out to MyTimetable; the class summary has term
  dates but not the weekly pattern.
- **Reliable historical conveners** — class summary pages for past years do
  survive, but the un-prefixed `/course/{CODE}/{Period}/{Number}` form that
  older links and older saved data use now redirects to an error page. Use the
  year-prefixed form.
- **Graduate attribute tags** — course pages carry a Graduate Attributes field
  that neither this document's recipes nor the CLI's parsers capture; read it
  off the HTML if you need it.

## 7. Etiquette

This is a public university website with no published API contract. Pause
between requests (the CLI uses half a second), don't fan out hundreds of
parallel fetches, and identify yourself in the User-Agent if your tool lets
you. A whole COMP catalogue is 20 JSON requests; a whole year of COMP course
pages is ~200 — do the former when it answers the question.

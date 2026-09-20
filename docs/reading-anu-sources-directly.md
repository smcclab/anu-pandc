# Reading the other ANU sources directly

**This is a fallback. If you can run `anu-pandc`, stop reading and run it.**

Its companion, [reading-pandc-directly.md](reading-pandc-directly.md), covers
Programs & Courses. This one covers the four sources the CLI reads alongside
it: the **Policy Library**, **University legislation**, the **class timetable**
and the **university calendar**. Same caveat as the companion — hand-fetching
re-derives parsers that already exist, and the CLI is the right answer wherever
it runs:

```bash
uvx --from git+https://github.com/smcclab/anu-pandc.git anu-pandc policy get ANUP_004603
```

Everything below was checked against the live sites on 2026-09-20.

## What lives where

A question about coursework usually needs more than one of these, and they
answer different kinds of question. Getting the source wrong is the commonest
way to give a confidently wrong answer.

| Question | Source |
|----------|--------|
| What must happen? Who may decide it? | **Legislation** — Statutes, Rules, Orders. Binding, federal law. |
| How does the University apply that? | **Policy Library** — policy, then procedure under it. |
| What does this course require of a student? | **P&C** course page, then the **class summary** for the real assessment. |
| When does it happen, university-wide? | **University calendar** — census, breaks, exam periods, results. |
| When and where does a class meet? | **MyTimetable** — scheduled, not delivered. |

Legislation beats policy, policy beats procedure, and a class summary beats all
of them for what a particular class actually did. If a policy and a Rule
disagree, the Rule wins and the policy is out of date.

## 1. The ANU Policy Library

Base: `https://policies.anu.edu.au`. Server-rendered HTML; no JavaScript
needed, no year in any URL — a document has an effective date, and only the
current version is published. Documents are numbered `ANUP_004603`.

| What | URL |
|------|-----|
| One document | `/ppl/document/ANUP_004603` |
| Every document, A–Z | `/ppl/title/index.htm` (≈495 rows, one page) |
| Everything of one type | `/ppl/view_all/index.htm?subdoctype_id=Policy` |
| Everything under a topic | `/ppl/view_all/index.htm?ssTopic=Students&ssSubTopic=Assessment` |
| Keyword search | `/ppl/search_results/index.htm?searchtype=QUICK&ssUserFullText=delegated+authority` |

`subdoctype_id` is one of `Policy`, `Procedure`, `Standard`, `Guideline`,
`Form`.

A document page has three parts worth reading:

- `div#convertedcontent` — the document body, converted from Word.
- `div#info_block` — a two-column table of the governance metadata: document
  type and number, **effective date**, **next review date**, **responsible
  officer**, **approved by**, **contact area**, and **Authority**, which links
  the legislation the document is made under. This is what tells you whether a
  document still binds anyone.
- a Related Content box linking the policy to its procedures and forms.

### Gotchas

- **Clause numbers are in the markup, not the text.** A policy cites its own
  clauses ("in accordance with Clause 73"), and a single run of clauses is
  split across dozens of `<ol>` elements, each carrying `start="13"`. Read
  `start`, or every number you quote will be wrong.
- Lettered sub-clauses are `<ol type="a">` and roman ones `<ol type="i">`.
- The page leaks its templating language into HTML comments
  (`convStringANU = wcmDynamicConversion(...)`). Drop comments before taking
  text, or they land in the middle of the document.
- **Search shows only the first five hits per document type**, with the true
  count in the group heading ("Policies (5 of 9)"). Use `view_all` for the
  rest. The "View all" link the page offers has the wrong `subdoctype_id` on
  it; build the URL yourself.
- The "Contact Area" column is sometimes an internal officer id
  (`260820251156`) rather than a name. That is the site's own quirk.
- A "Printable version (PDF)" link is `/ppl/pdfdownload/<n>`, where `<n>` is
  unrelated to the document number.

## 2. University legislation

ANU's Statutes, Rules and Orders are made by Council or the Vice-Chancellor
under s 50 of the *Australian National University Act 1991*. They have the
status of federal law and are registered on the Federal Register of
Legislation. That means two sources, and you need both.

**What applies to ANU** — `https://www.anu.edu.au/about/governance/legislation`.
Server-rendered, grouped under `h3` into Acts, Statutes, Rules and Orders, each
item a `ul.linklist` entry linking to an ANU page. The Register has no way to
ask "everything ANU made", so this list is the answer to which titles count.
The ANU index page carries no Register ids; an item's own page does, in the
deep links to the document text.

**Status and text** — the Register.

- Metadata, OData: `https://api.prod.legislation.gov.au/v1/titles?$filter=...`
  ```
  $filter=contains(name,'Coursework Awards Rule') and isInForce eq true
  $select=id,name,collection,subCollection,status,isInForce,isPrincipal,makingDate
  $expand=authorisedBy,versions
  ```
- Human page, and the one to cite:
  `https://www.legislation.gov.au/F2024L01752/latest/text`
- **Document text**, which is what you actually want:
  ```
  https://www.legislation.gov.au/{id}/latest/{version-start-date}/text/original/epub/OEBPS/document_1/document_1.html
  ```
  where `{version-start-date}` is `YYYY-MM-DD`, taken from the `isLatest`
  entry in `versions`.

### Gotchas

- **`/latest/text` without a date is a JavaScript shell.** It returns ~76 KB of
  Angular and no document. The date-bearing EPUB URL above is the text. So a
  fetch is always two requests: OData for the version date, then the text.
- **The text is served with no charset.** `requests` then guesses ISO-8859-1
  and every em dash becomes `â€”`. Decode as UTF-8, or hand the bytes to a
  parser that reads the document's own declaration.
- `$orderby` is rejected by the API (HTTP 400). Sort client-side.
- So is any `$filter` over `authorisedBy` — the server throws a LINQ error. You
  can read `authorisedBy` with `$expand`, you just cannot filter on it. Which
  is why enumerating ANU's instruments goes through the ANU index page.
- **A name matches every version ever made.** "Coursework Awards Rule" returns
  sixteen titles, fifteen of them repealed. Filter on `isInForce` and
  `isPrincipal`, and check `status` before quoting anything.
- ANU's education Rules do *not* have "Australian National University" in their
  names — *Coursework Awards Rule 2024*, *Academic Integrity Rule 2021*,
  *Assessment Rule 2016*. Searching the Register for the University's name
  finds the Statutes and misses the Rules.
- Ids: `C####A#####` an Act, `F####L#####` a legislative instrument,
  `F####N#####` notifiable, `C####G#####` a gazette notice.

## 3. The class timetable (Allocate+ Web Publisher)

`https://mytimetable.anu.edu.au` is a JavaScript application over a small REST
backend, so fetching the page gets you an empty shell. Query the backend.

There are two instances, one per parity of the year: `/even/` currently holds
2026 and `/odd/` 2025. There is no year parameter — **the instance is the
year** — so any other year cannot be read here at all.

```bash
curl -s -X POST https://mytimetable.anu.edu.au/even/rest/timetable/subjects \
  --data 'search-term=COMP3300&days=1&days=2&days=3&days=4&days=5&days=6&days=0&start-time=00:00&end-time=23:00'
```

The response is a JSON object keyed by offering (`COMP3300_S2_1_8682`, whose
last segment is the P&C class number). Each offering has `manager` (a person —
the only name in this data), `children` (co-taught offerings), and
`activities`, a dict of activity records with `activity_group_code` (LecA,
ComA…), `activity_code`, `activity_type`, `day_of_week`, `start_time`,
`duration` in minutes, `location`, `description`, `semester_description`,
`week_pattern`, and `activitiesDays` — the explicit list of dates as `d/m/yyyy`.

Other endpoints under `../rest/timetable/`: `locations` and `studentsets`
(POST searches), `subject/<code>/sections`, `subject/<code>/activity_groups`,
`locations/<subject>/<group>/<activity>`.

### Gotchas

- **Count sessions from `activitiesDays`**, not by decoding `week_pattern`.
- **Drop `activity_type: "Clone"`.** Those duplicate a real slot, carry no
  location, and double every count made over them.
- **Several streams of one group are alternatives.** ComA/01–04 are four
  offerings of the same lab; a student attends one. Counting all four turns 5
  contact hours into 20.
- `staff` is almost always `-`. The timetable does not say who teaches. The
  convener is on the class summary in P&C.
- Co-taught codes are in `description`
  (`COMP3300_S2_(01)-ComA/01 + COMP6330_S2_(01)-ComA/01`). A code is followed
  by an underscore, which is a word character, so `\bCOMP\d{4}\b` never
  matches. Use a lookahead.
- This is the **scheduled** timetable. It changes, and it is not evidence that
  anything was delivered. Required contact hours come from P&C and the class
  summaries; check the dates against the calendar's teaching breaks and public
  holidays.

## 4. The university calendar

Published twice, as a page and as a feed:

| Purpose | URL |
|---------|-----|
| The page, and the thing to cite | `https://www.anu.edu.au/directories/university-calendar?year=YYYY` |
| Machine-readable | `https://www.anu.edu.au/directories/university-calendar/YYYY/calendar.ics` |

The feed works for 2026 (55 events) and 2027 (62), and is served with
`cache-control: max-age=900`, so it is near-live. Each `VEVENT` has `DTSTART`,
`SUMMARY` and `URL`.

### Gotchas

- **Every event is a single day.** There is no `DTEND`; a range is published as
  two events, "… begins" and "… ends". Pair them yourself.
- **The wording of the pairs drifts.** A break "commences" and you "Return
  from" it — the marker is at the *front* of the closing summary. The
  Semester 1 examination period has no "begins" at all, only an "ends". A
  deferred period is "… period 1 begins (two week duration)", with the marker
  before a parenthetical. And one pair in 2026 opens with a hyphen and closes
  with an en dash. Match on keywords, and normalise before comparing.
- **`DTSTART` is `T000000Z`** although the date meant is the Canberra local
  one. Read the date part only. Converting the timezone moves Semester 1
  census day from 31 March to the 30th.
- HTML entities appear in `SUMMARY` (`&#039;`); unescape them.
- The `audience` filter is unreliable — `?audience=` on the feed returns all
  events regardless. Filter yourself.
- Page metadata reports `modified_time` 2024-10-14 even for 2027 content, so it
  tells you nothing about freshness. Cross-check any date you will rely on
  against the HTML page, and cite that page.
- These are university-wide dates. Course assessment dates are in the class
  summaries; school deadlines (curriculum rounds, class summary due dates) are
  published somewhere else entirely.

## Network

These are the hosts involved, for an egress allow-list:

```
programsandcourses.anu.edu.au   programs, courses, class summaries
policies.anu.edu.au             the Policy Library
mytimetable.anu.edu.au          the class timetable
www.anu.edu.au                  the university calendar, the legislation index
api.prod.legislation.gov.au     Register metadata
www.legislation.gov.au          Register document text
```

A 403 carrying an `x-deny-reason` header is your own gateway, not ANU, and no
header or proxy change gets around it. `anu-pandc` says which of the two
refused you.

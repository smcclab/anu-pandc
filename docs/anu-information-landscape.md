# ANU's student-facing course information

This is a survey of where ANU publishes what a student needs to know about a
course, and of the practical problems with how it is published. It comes from
building `anu-pandc`, which reads every one of these sources, so it is written
from the point of view of someone trying to get a correct answer out of them,
whether that someone is a student, a staff member or a program.

It covers only public, unauthenticated pages. The student records system, the
learning management system and school websites are out of scope. The details
were checked against the live sites in September 2026. The companion
documents [reading-pandc-directly.md](reading-pandc-directly.md) and
[reading-anu-sources-directly.md](reading-anu-sources-directly.md) give the
URL shapes and parsing recipes; this one is about the overall picture.

## The map

A student question about a course touches up to seven systems, each run
separately:

| Question | Where the answer is | What it is |
|----------|--------------------|------------|
| What is this course, and what does it require? | [Programs & Courses](https://programsandcourses.anu.edu.au) (P&C) course page | Azure web app, one set of pages per year |
| What is the actual assessment, with due dates? Who convenes it? | P&C class summary | A separate page per class number, linked from the course page |
| When and where do classes meet? | [MyTimetable](https://mytimetable.anu.edu.au) | Allocate+ JavaScript app over a REST backend |
| When and where is the exam? | [Exam timetable](https://exams.anu.edu.au/timetable/login.php?db=0) | PHP search form, open only part of the year |
| What week is it? When is census, the break, the exam period? | [University calendar](https://www.anu.edu.au/directories/university-calendar) | Web page plus an iCalendar feed |
| How does the University apply a rule? | [Policy Library](https://policies.anu.edu.au) | Documents converted from Word |
| What is binding, and who may decide it? | ANU's [legislation index](https://www.anu.edu.au/about/governance/legislation), then the [Federal Register of Legislation](https://www.legislation.gov.au) | ANU page, then a Commonwealth system |

For what a particular class did, the order of authority is: legislation, then
policy, then procedure. The class summary beats all of them.

### School course websites are not on this list

Some schools run public course websites; the School of Computing's are at
`comp.anu.edu.au/courses/<code>/`. They look official, often carry more
detail than the class summary, and rank well in search. But they are
**non-official course material**. They can be out of date without warning,
may not be in use at all, and can sit unattended for years. The class summary
is the only official listing of what is in a course (the Canvas course site
is also maintained, but it sits behind a login). Treat a course website as
evidence of what a course contains only where it clearly agrees with the
class summary for the same year and period.

## Problems that cut across the systems

### Nothing links the systems together

Each system answers its own question well enough. But a typical student
question ("when is my COMP2100 exam, and is that in the exam period?") needs
three of them, and nothing leads from one to the next:

- A P&C course page links to MyTimetable, but not to the course's exam or to
  the calendar dates it depends on.
- A class summary may have an Examination(s) section describing the exam. It
  does not give the date or the room; those are on the exam timetable.
- The timetable knows nothing about the calendar, and the exam timetable
  knows nothing about P&C.

The only thing the systems have in common is the course code, and even that
is not written the same way everywhere:

| System | How a course appears |
|--------|---------------------|
| P&C | `COMP3300`, with a separate per-year class number (`8682`) |
| MyTimetable | `COMP3300_S2_1_8682` as a key; co-taught courses named only in a free-text description (`COMP3300_S2_(01)-ComA/01 + COMP6330_S2_(01)-ComA/01`) |
| Exam timetable | `COMP3300_Semester 2 / 3300`; co-taught courses combined (`COMP1110/COMP1140/COMP6710_Semester 2`) |

**Consequence.** The student has to know which systems exist, visit each one
separately, and match the results up by hand.

**What would help.** A class summary that links to its own timetable entry,
its exam once published, and the calendar dates it uses (census, the
teaching break, the exam period).

### Each system handles time differently

Most of the bugs found while building this tool came from dates, and each
system has its own model of time:

- **P&C** keeps one set of pages per year, and there is no "current year"
  URL. But a course page for 2026 also carries planned class rows for 2027
  and 2028, and program pages for a future year appear before their majors
  and courses do.
- **MyTimetable** has no year parameter. It runs two instances, one for even
  years and one for odd, so only two years can be read at any time. The
  design implies that each year is replaced when its instance moves on two
  years later. A search returns every
  teaching period of the year at once, as a weekly pattern. Only the list of
  dates attached to each activity says which weeks it actually runs.
- **The calendar** has no date ranges. A range is published as two
  single-day events, and the closing wording carries different meanings:
  "Semester 1 ends" includes that day, while "Return from teaching break" is
  the first day *back*. Reading both the same way made the 2026 Semester 2
  break appear to run until 21 September, hiding a full week of teaching. The
  wording also varies between years ("begins", "commences", a missing
  "begins" for the Semester 1 exam period). Events are stamped as midnight
  UTC but mean the Canberra date, so converting timezones moves Semester 1
  census from 31 March to 30 March.
- **The exam timetable** exists only while an exam event is open (see below).

**Consequence.** A reader who applies common sense to one system gets a
wrong date from another. Under a date-range reading that looks reasonable, a
scheduled class can appear to fall inside a teaching break.

**What would help.** Explicit start and end dates for calendar ranges, and a
stated year on everything that is year-specific.

### Some pages don't exist until released, and "missing" can mean several things

- The exam timetable is empty for most of the year.
- A future year's program page can be published before its majors and
  courses.
- The link to a future year's class summary reads `N/A`, so the convener for
  next year is simply not published.
- An unknown P&C code does not return a 404. It redirects to an error page
  that answers HTTP 200.
- Old-style class summary URLs without a year now redirect to an error page,
  so older saved links have broken.

**Consequence.** From outside, "not published yet", "does not exist" and "you
asked for the wrong thing" look identical. A student cannot tell whether to
wait, give up or try another URL, and automated tools have to inspect page
bodies to detect errors.

**What would help.** A real 404 for things that don't exist, and a short
"not yet published — expected around …" notice for things that will.

### The version students see first is not the one that holds

- The P&C course page shows *indicative* assessment. The real schedule, with
  due dates, is on the class summary, one click and one class number away,
  and often differs.
- MyTimetable is the *scheduled* timetable. It changes, and it lists the
  staff as `-`, so it does not say who teaches. The convener is on the class
  summary.
- The calendar page is the one to cite, but its metadata reports a 2024
  modification date even for 2027 content, so it gives no signal of how
  fresh it is. The exam timetable's footer likewise says "Updated 3 July
  2024" above a timetable for November 2026.

**What would help.** Put a prominent link from the course page's assessment
section to the class summary, and use modification dates that reflect the
content.

## System by system

### Programs & Courses

- The catalogue search API caps pages at 10 results whatever size is
  requested, matches titles as well as codes, and silently ignores most of
  its filters.
- The search API's `Session` field is not a teaching plan. Research shells
  list every session of the year, which means "enrol any time", not "taught
  six times". Only the course page's class tab gives the real offerings.
- Conveners are named inconsistently across years (with and without
  honorifics, and under different spellings), and a list of several
  conveners does not distinguish co-convening from convener-plus-guest.

### MyTimetable

- The page is empty until JavaScript runs. The data sits behind a REST
  backend that has no public documentation.
- Parallel streams of one activity (four lab streams, say) are alternatives:
  a student attends one. Summing them overstates contact hours four times
  over.
- "Clone" activities duplicate real slots with no location. Counting them
  doubles everything.

### Exam timetable

- **Events are only visible while open.** Each exam event is released when
  the Examinations Office is ready and closes on a fixed date. After that its
  page says only "not available after DD/MM/YYYY".
- **The URLs are reused.** Events are addressed as `login.php?db=N`, and
  `N` is a reused slot, not an identifier. `db=14` held Semester 1 2024,
  `db=1` Semester 1 2025, `db=13` Semester 2 2026. A saved link will later
  point at a different semester's exams. The only reliable way in is the
  `db=0` index; the design seems to assume students arrive from a link in an
  email.
- **It depends on hidden session state.** Results come 20 at a time, and the
  "next" link carries neither the event nor the search; the server remembers
  both against a session cookie. A session that has searched one event gets
  an HTTP 500 if it searches another without first reloading that event's
  page.
- **One exam, many rows.** A large exam is listed once per room (COMP1730 has
  seven), and the timetable does not say which room a given student sits in.
- Columns differ between events: the in-class event has no reading time or
  room.

### University calendar

- Covered above: single-day events, "Return from" meaning the first day
  back, wording that changes between years, and UTC stamps on local dates.
- HTML entities appear inside event titles in the feed.
- The feed's `audience` filter is ignored; every event comes back.

### Policy Library

- Clause numbers exist only in the page markup (the `start` attribute of
  numbered lists). Policies cite their own clauses ("in accordance with
  Clause 73"), and copying the text loses the numbering those references
  depend on.
- Search shows five results per document type, and the "View all" link it
  offers has the wrong filter in it.
- "Contact Area" is sometimes an internal officer id rather than a name.
- Templating code leaks into HTML comments in the middle of documents.

### Legislation

The Federal Register is a Commonwealth system outside ANU's control, so its
design is a given rather than something to fix here. Two things about it
shape how ANU's legislation can be found:

- The Register cannot list "everything ANU made", so ANU's own
  [legislation index](https://www.anu.edu.au/about/governance/legislation)
  is the only list of what applies. That index carries no Register ids; each
  item's own ANU page has to be opened to find where its text lives.
- ANU's education Rules do not have "Australian National University" in
  their names (*Coursework Awards Rule 2024*, *Assessment Rule 2016*), so
  searching the Register for the University finds the Statutes and misses the
  Rules that govern coursework.

The part ANU controls is its index. Putting each instrument's Register id and
a direct link to its current text on the index would remove a step and a
source of wrong answers.

## What would help most

In rough order of how many wrong answers each would prevent:

1. **Link the class summary to everything else about the class**: its
   timetable, its exam once published, and the calendar dates it depends on.
2. **Publish calendar ranges as ranges**, with explicit start and end dates
   and consistent wording.
3. **Give exam events stable addresses**: a URL that names the year and
   period, and a note on the index saying when the next timetable is
   expected.
4. **Make "missing" honest**: 404s for things that don't exist, and "not yet
   published" notices for things that will.
5. **Use one course identifier everywhere**, with co-taught courses listed as
   data rather than embedded in free text or combined codes.

None of these would require the systems to be merged. Each is a link, a
field or a status code.

# Programs & Courses JSON API reference

The P&C catalogue page (`programsandcourses.anu.edu.au/catalogue`) is backed by
JSON endpoints under `/data/`. These return structured data directly — no HTML
parsing needed. Surveyed 2026-07-04.

## Endpoints

All accept `SearchText`, `PageIndex`, `MaxPageSize`, `SelectedYear` as query params.

| Endpoint | Returns | Notes |
|----------|---------|-------|
| `/data/CourseSearch/GetCourses` | Course code, title, career, units, mode, sessions | Used by `anu-pandc catalogue`. `AppliedFilter=FilterByCourses` |
| `/data/MajorSearch/GetMajors` | SubPlanCode, name, units, career | 135 majors in 2026; empty `SearchText` returns all |
| `/data/MinorSearch/GetMinors` | Same shape as majors | |
| `/data/SpecialisationSearch/GetSpecialisations` | Same shape; SubplanType field | 153 specs in 2026 |
| `/data/ProgramSearch/GetProgramsUnderGraduate` | AcademicPlanCode, name, ATAR, duration, CanCombine, mode | Also `...PostGraduate`, `...Research`, `...NonAward` |

## Quirks (observed)

- **Page size is capped at 10** regardless of `MaxPageSize` — always paginate
  with `PageIndex` until `TotalCount` items are collected.
- **`SearchText` matches titles as well as codes** — filter results client-side
  on the code prefix (e.g. `CourseCode.startswith("COMP")`).
- **Server-side filters mostly don't work**: `Semesters=` and the
  `FilterByMajors/Minors/Specialisations` values on `GetCourses` are ignored.
  `Careers=Undergraduate` on `GetCourses` DOES work. Safest to fetch broadly
  and filter locally on the returned `Session` / `Career` fields.
- **Historical years work**: `SelectedYear` accepted back to at least 2015
  (213 COMP matches in 2015, 250 in 2020, 222 in 2024). Sessions per year are
  included, so year-by-year offering tables can be built without scraping any
  course pages.
- Zero-result queries return a `Suggestion` field (spelling correction).

## Example

```
curl "https://programsandcourses.anu.edu.au/data/CourseSearch/GetCourses?\
AppliedFilter=FilterByCourses&SearchText=COMP&PageIndex=0&MaxPageSize=50&SelectedYear=2026"
```

`scraper/scrape_catalogue.py` wraps `GetCourses`; the subplan and program
endpoints are not yet wrapped.

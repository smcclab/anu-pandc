"""anu-pandc command line."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.logging import RichHandler

from anu_pandc import __version__, codes, http, legislation, policy, timetable
from anu_pandc.catalogue import (FIELDS as CATALOGUE_FIELDS, catalogue_rows,
                                 catalogue_to_markdown, fetch_catalogue, teaching_codes)
from anu_pandc.conveners import (FIELDS as CONVENER_FIELDS, collect as collect_conveners,
                                 conveners_to_markdown, load_aliases)
from anu_pandc.offerings import (FIELDS as OFFERING_FIELDS, course_from_markdown,
                                 offerings_to_markdown, rows_by_year)
from anu_pandc.render import emit, err, status, rows_to_csv, rows_to_json
from anu_pandc.scrape import Item, class_targets, fetch_class, fetch_item
from anu_pandc.store import Store, now_iso

log = logging.getLogger("anu_pandc")

ITEM_FORMATS = ["md", "json"]
TABLE_FORMATS = ["md", "csv", "json"]
POLICY_DOC_TYPES = ["Policy", "Procedure", "Standard", "Guideline", "Form"]


def _formats(value: tuple[str, ...], default: str = "md") -> list[str]:
    return list(dict.fromkeys(value)) or [default]


def _year_option(f):
    return click.option("--year", "-y", required=True, help="Catalogue year, e.g. 2026.")(f)


def _save_option(f):
    return click.option("--save", "-s", "save_dir", type=click.Path(file_okay=False),
                        help="Write into this directory tree instead of printing. "
                             "Files land in SAVE/<year>/{programs,subplans,courses,classes}/.")(f)


def _force_option(f):
    return click.option("--force", is_flag=True, help="Re-fetch pages already saved.")(f)


def _plain_option(f):
    return click.option("--plain", is_flag=True, help="Print raw Markdown; no terminal rendering.")(f)


def _fail(message: str) -> None:
    status(f"error: {message}", "red")
    sys.exit(1)


# ---- group -------------------------------------------------------------------


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="anu-pandc")
@click.option("--rate", type=float, default=None, metavar="SECONDS",
              help="Pause between requests (default 0.5).")
@click.option("-v", "--verbose", is_flag=True, help="Show every fetch.")
@click.option("-q", "--quiet", is_flag=True, help="Only show errors.")
def cli(rate, verbose, quiet):
    """A command-line interface to ANU Programs & Courses.

    Point it at any program, major/minor/specialisation or course code and a
    year. Print the page as Markdown or JSON, or save a whole tree of them.

    \b
    Examples:
      anu-pandc get COMP1730 --year 2026
      anu-pandc get BCOMP --year 2026 --json
      anu-pandc get BCOMP --year 2026 --save ./data --recursive
      anu-pandc catalogue COMP --year 2026 --save ./data
      anu-pandc classes COMP1730 --year 2026
    """
    if rate is not None:
        http.rate_limit_seconds = rate
    level = logging.ERROR if quiet else logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s",
                        handlers=[RichHandler(console=err, show_time=False, show_path=False,
                                              show_level=False, markup=False)])


# ---- get ---------------------------------------------------------------------


def _save_item(store: Store, item: Item, formats: list[str]) -> list[Path]:
    paths = []
    for fmt in formats:
        path = store.item_path(item.year, item.kind, item.code, fmt)
        store.write(path, item.render(fmt))
        paths.append(path)
    store.log(item.year, f"{store.item_path(item.year, item.kind, item.code).relative_to(store.year_dir(item.year))} — {item.url}")
    return paths


def _already_saved(store: Store, year: str, kind: str, code: str, formats: list[str]) -> bool:
    return all(store.item_path(year, kind, code, fmt).exists() for fmt in formats)


@cli.command(short_help="Fetch programs, subplans or courses by code.")
@click.argument("codes_", metavar="CODE...", nargs=-1, required=True)
@_year_option
@click.option("--kind", type=click.Choice(["program", "subplan", "course"]),
              help="Override the page type inferred from the code's shape.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(ITEM_FORMATS),
              help="Output format(s). Default md. Repeat for both.")
@click.option("--json", "as_json", is_flag=True, help="Shorthand for --format json.")
@_save_option
@click.option("--recursive", "-r", is_flag=True,
              help="For a program: also fetch its majors/minors/specialisations and "
                   "then every course any of them names. For a subplan: its courses.")
@_force_option
@_plain_option
def get(codes_, year, kind, formats, as_json, save_dir, recursive, force, plain):
    """Fetch one or more programs, subplans or courses.

    The page type is inferred from the code: COMP1100 is a course, COMS-MAJ /
    HCCC-MIN / ARTIF-SPEC are subplans, anything else (BCOMP, 7706XMCOMP) is a
    program. Without --save the result is printed; with --save it is written
    under SAVE/<year>/ and the course codes it mentions are added to
    SAVE/<year>/course-codes.txt.
    """
    formats = _formats(formats + (("json",) if as_json else ()))
    store = Store(save_dir) if save_dir else None
    if recursive and not store:
        _fail("--recursive only makes sense with --save DIR")

    queue: list[tuple[str, str | None]] = [(codes.normalise(c), kind) for c in codes_]
    seen: set[tuple[str, str]] = set()
    discovered_courses: set[str] = set()
    errors = 0
    fetched = skipped = 0

    while queue:
        code, k = queue.pop(0)
        k = k or codes.kind_of(code)
        if (k, code) in seen:
            continue
        seen.add((k, code))

        if store and not force and _already_saved(store, year, k, code, formats):
            skipped += 1
            status(f"[skip] {k} {code}", "dim")
            if recursive:
                # Still need what this saved page names; re-read it from disk cheaply
                # by re-fetching only when the on-disk copy cannot tell us.
                item = _reload_or_fetch(store, code, year, k)
            else:
                continue
        else:
            try:
                item = fetch_item(code, year, k)
            except Exception as exc:  # noqa: BLE001 - report and continue
                errors += 1
                status(f"[error] {k} {code}: {exc}", "red")
                continue
            fetched += 1
            if store:
                for path in _save_item(store, item, formats):
                    status(f"→ {path}", "green")
            else:
                for fmt in formats:
                    emit(item.render(fmt), fmt, plain)

        if store and k in ("program", "subplan"):
            discovered_courses |= item.course_codes()
        if recursive:
            if k == "program":
                queue.extend((s, "subplan") for s in sorted(item.subplan_codes()))
            if k in ("program", "subplan"):
                queue.extend((c, "course") for c in sorted(item.course_codes()))

    if store and discovered_courses:
        new, total = store.merge_codes(year, discovered_courses)
        status(f"[codes] +{new} course codes → {store.codes_path(year)} ({total} total)")
    if store:
        status(f"[done] fetched={fetched} skipped={skipped} errors={errors}")
    sys.exit(1 if errors else 0)


def _reload_or_fetch(store: Store, code: str, year: str, kind: str) -> Item:
    """Rebuild enough of an Item from a saved page to continue a recursive walk.

    The saved Markdown lists every course code and subplan code the page named,
    so a regex over it is sufficient; no network needed.
    """
    path = store.item_path(year, kind, code, "md")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text:
        return fetch_item(code, year, kind)
    data = {
        "all_course_codes": sorted(codes.course_codes_in(text)),
        "specialisations": [{"items": [{"code": s} for s in sorted(codes.subplan_codes_in(text))]}],
    }
    return Item(kind, code, year, codes.url_for(code, year, kind), data)


# ---- courses (bulk) ----------------------------------------------------------


@cli.command(short_help="Bulk-fetch every course in a saved tree's code list.")
@click.argument("codes_", metavar="[CODE...]", nargs=-1)
@_year_option
@click.option("--save", "-s", "save_dir", type=click.Path(file_okay=False), required=True,
              help="Tree to read course-codes.txt from and write course pages into.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(ITEM_FORMATS))
@click.option("--prefix", help="Only codes starting with this subject prefix, e.g. COMP.")
@_force_option
def courses(codes_, year, save_dir, formats, prefix, force):
    """Bulk-fetch course pages for every code in SAVE/<year>/course-codes.txt.

    Run after `get PROGRAM --recursive` and/or `catalogue PREFIX` have filled
    the code list. Pass codes explicitly to fetch just those.
    """
    formats = _formats(formats)
    store = Store(save_dir)
    todo = [codes.normalise(c) for c in codes_] or sorted(store.read_codes(year))
    if prefix:
        todo = [c for c in todo if c.startswith(prefix.upper())]
    if not todo:
        _fail(f"no course codes found in {store.codes_path(year)}; run `get PROGRAM --recursive` or `catalogue` first")

    fetched = skipped = errors = 0
    for code in todo:
        if not force and _already_saved(store, year, "course", code, formats):
            skipped += 1
            continue
        try:
            item = fetch_item(code, year, "course")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            status(f"[error] {code}: {exc}", "red")
            continue
        fetched += 1
        for path in _save_item(store, item, formats):
            status(f"→ {path}", "green")
    status(f"[done] fetched={fetched} skipped={skipped} errors={errors} (of {len(todo)})")
    sys.exit(1 if errors else 0)


# ---- classes -----------------------------------------------------------------


@cli.command(short_help="Fetch class summaries (convener, dates, assessment).")
@click.argument("codes_", metavar="[CODE...]", nargs=-1)
@_year_option
@click.option("--period", "-p", help='Only this teaching period, e.g. "First Semester".')
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(ITEM_FORMATS))
@click.option("--json", "as_json", is_flag=True, help="Shorthand for --format json.")
@_save_option
@click.option("--prefix", help="With no CODE: only codes starting with this prefix.")
@_force_option
@_plain_option
def classes(codes_, year, period, formats, as_json, save_dir, prefix, force, plain):
    """Fetch class summary pages (convener, dates, real assessment) for courses.

    A course page lists its classes for the year; each live class links to a
    summary page. All periods are fetched unless --period narrows it. With no
    CODE and --save, every code in SAVE/<year>/course-codes.txt is used.
    """
    formats = _formats(formats + (("json",) if as_json else ()))
    store = Store(save_dir) if save_dir else None
    todo = [codes.normalise(c) for c in codes_]
    if not todo:
        if not store:
            _fail("give at least one CODE, or --save DIR to use its course-codes.txt")
        todo = sorted(store.read_codes(year))
        if prefix:
            todo = [c for c in todo if c.startswith(prefix.upper())]
        if not todo:
            _fail(f"no course codes in {store.codes_path(year)}")

    fetched = skipped = errors = no_summary = 0
    for code in todo:
        try:
            course = fetch_item(code, year, "course")
        except Exception as exc:  # noqa: BLE001
            errors += 1
            status(f"[error] {code} (course page): {exc}", "red")
            continue
        targets = class_targets(course, year, period)
        if not targets:
            no_summary += 1
            status(f"[no-summary] {code} {year}{' ' + period if period else ''}", "dim")
            continue
        for offering in targets:
            paths = [store.class_path(year, code, offering["semester"], offering["class_number"], f)
                     for f in formats] if store else []
            if store and not force and all(p.exists() for p in paths):
                skipped += 1
                continue
            try:
                item = fetch_class(code, year, offering)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                status(f"[error] {code} class {offering['class_number']}: {exc}", "red")
                continue
            fetched += 1
            if store:
                for fmt, path in zip(formats, paths):
                    store.write(path, item.render(fmt))
                    status(f"→ {path}", "green")
                store.log(year, f"classes/{paths[0].name} — {item.url}")
            else:
                for fmt in formats:
                    emit(item.render(fmt), fmt, plain)
    status(f"[done] fetched={fetched} skipped={skipped} no-summary={no_summary} errors={errors}")
    sys.exit(1 if errors else 0)


# ---- catalogue ---------------------------------------------------------------


@cli.command(short_help="List every course under a subject prefix.")
@click.argument("prefix")
@_year_option
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_save_option
@click.option("--include-research", is_flag=True,
              help="Also add Research-career codes (HDR shells) to course-codes.txt.")
@click.option("--no-merge", is_flag=True, help="Don't touch course-codes.txt when saving.")
@_plain_option
def catalogue(prefix, year, formats, save_dir, include_research, no_merge, plain):
    """List every course under a subject PREFIX (e.g. COMP) for a year.

    Uses the P&C search API, so it also finds courses no program page names.
    With --save, writes SAVE/<year>/catalogue-PREFIX.<fmt> and merges the
    teaching-course codes into course-codes.txt for `courses` to pick up.
    """
    prefix = prefix.upper()
    formats = _formats(formats)
    entries = fetch_catalogue(prefix, year)
    if not entries:
        _fail(f"no {prefix} courses in the {year} catalogue")
    scraped_at = now_iso()
    renders = {
        "md": lambda: catalogue_to_markdown(entries, prefix, year, scraped_at),
        "csv": lambda: rows_to_csv(catalogue_rows(entries), CATALOGUE_FIELDS),
        "json": lambda: rows_to_json(catalogue_rows(entries)),
    }
    if not save_dir:
        for fmt in formats:
            emit(renders[fmt](), fmt, plain)
        return
    store = Store(save_dir)
    for fmt in formats:
        path = store.write(store.table_path(year, "catalogue", prefix, fmt), renders[fmt]())
        status(f"→ {path}", "green")
    store.log(year, f"catalogue-{prefix} — search API, {len(entries)} courses")
    if not no_merge:
        new, total = store.merge_codes(year, teaching_codes(entries, include_research))
        status(f"[codes] +{new} course codes → {store.codes_path(year)} ({total} total)")


# ---- offerings ---------------------------------------------------------------


@cli.command(short_help="Planned sittings per course, by offering year.")
@click.argument("codes_", metavar="[CODE...]", nargs=-1)
@_year_option
@click.option("--from", "from_dir", type=click.Path(exists=True, file_okay=False),
              help="Saved tree to read course pages from (default: fetch from the web).")
@click.option("--prefix", help="Only courses with this subject prefix (default: all).")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_save_option
@_plain_option
def offerings(codes_, year, from_dir, prefix, formats, save_dir, plain):
    """Planned sittings (session, class number, mode) per course, by offering year.

    Reads the "Offered in" table on the --year course pages. Those carry rows
    for later years too, so one table is produced per offering year found.
    Source is the saved tree given by --from, else the web (needs CODE... or
    --save DIR holding a course-codes.txt).
    """
    formats = _formats(formats, default="csv")
    prefix = prefix.upper() if prefix else None
    todo = [codes.normalise(c) for c in codes_]

    parsed: list[dict] = []
    if from_dir:
        store_in = Store(from_dir)
        files = store_in.course_files(year)
        if todo:
            files = [f for f in files if f.stem in todo]
        if prefix:
            files = [f for f in files if f.stem.startswith(prefix)]
        if not files:
            _fail(f"no saved course pages under {store_in.year_dir(year) / 'courses'}")
        parsed = [course_from_markdown(f) for f in files]
    else:
        if not todo and save_dir:
            todo = sorted(Store(save_dir).read_codes(year))
        if prefix:
            todo = [c for c in todo if c.startswith(prefix)]
        if not todo:
            _fail("give CODE..., or --from DIR, or --save DIR with a course-codes.txt")
        for code in todo:
            try:
                parsed.append(fetch_item(code, year, "course").data)
            except Exception as exc:  # noqa: BLE001
                status(f"[error] {code}: {exc}", "red")

    by_year = rows_by_year(parsed)
    if not by_year:
        _fail("no offerings found on those pages")

    label = prefix or "ALL"
    store_out = Store(save_dir) if save_dir else None
    for offering_year in sorted(by_year):
        rows = by_year[offering_year]
        renders = {
            "csv": lambda: rows_to_csv(rows, OFFERING_FIELDS),
            "json": lambda: rows_to_json(rows),
            "md": lambda: offerings_to_markdown(rows, offering_year, year, prefix or ""),
        }
        if store_out:
            for fmt in formats:
                path = store_out.write(store_out.table_path(offering_year, "offerings", label, fmt), renders[fmt]())
                status(f"→ {path}  ({len(rows)} rows)", "green")
        else:
            if len(by_year) > 1:
                status(f"## offering year {offering_year}", "bold")
            for fmt in formats:
                emit(renders[fmt](), fmt, plain)


# ---- conveners ---------------------------------------------------------------


@cli.command(short_help="Who convened each saved class.")
@click.option("--from", "from_dir", type=click.Path(exists=True, file_okay=False), required=True,
              help="Saved tree whose <year>/classes/ pages to read.")
@click.option("--year", "-y", help="Only this year (default: every year in the tree).")
@click.option("--prefix", help="Only courses with this subject prefix.")
@click.option("--aliases", type=click.Path(exists=True, dir_okay=False),
              help="Name aliases: JSON object or lines of 'Variant = Canonical'.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@click.option("--output", "-o", type=click.Path(dir_okay=False), help="Write here instead of stdout.")
@_plain_option
def conveners(from_dir, year, prefix, aliases, formats, output, plain):
    """Table of who convened each saved class (from class summary pages).

    Run `classes ... --save DIR` first; this reads DIR, it does not fetch.
    """
    formats = _formats(formats, default="csv")
    rows = collect_conveners(Store(from_dir), prefix, year, load_aliases(aliases))
    if not rows:
        _fail(f"no class pages with a convener under {from_dir}")
    renders = {
        "csv": lambda: rows_to_csv(rows, CONVENER_FIELDS),
        "json": lambda: rows_to_json(rows),
        "md": lambda: conveners_to_markdown(rows),
    }
    if output:
        Path(output).write_text(renders[formats[0]](), encoding="utf-8")
        status(f"→ {output}  ({len(rows)} rows)", "green")
        return
    for fmt in formats:
        emit(renders[fmt](), fmt, plain)


# ---- policy library ----------------------------------------------------------


@cli.group("policy", short_help="ANU Policy Library: policies, procedures, forms.")
def policy_group():
    """Read the ANU Policy Library: policies, procedures, standards and forms.

    \b
    Examples:
      anu-pandc policy get ANUP_004603
      anu-pandc policy get "Student assessment (coursework)"
      anu-pandc policy search "delegated authority"
      anu-pandc policy list --type Policy -f csv
    """


def _resolve_policy_number(query: str) -> str:
    """A document number as given, or the best title match for a phrase."""
    try:
        return policy.normalise(query)
    except ValueError:
        pass
    rows, _ = policy.search(query)
    if not rows:
        _fail(f"nothing in the Policy Library matches {query!r}")
    exact = [row for row in rows if row["title"].lower() == query.lower()]
    return (exact or rows)[0]["number"]


@policy_group.command("get", short_help="Fetch one policy-library document.")
@click.argument("queries", metavar="NUMBER-OR-TITLE...", nargs=-1, required=True)
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(ITEM_FORMATS))
@click.option("--json", "as_json", is_flag=True, help="Shorthand for --format json.")
@_save_option
@_force_option
@_plain_option
def policy_get(queries, formats, as_json, save_dir, force, plain):
    """Fetch policy-library documents by number (ANUP_004603) or by title.

    A title is resolved through the library's own search, so a phrase that
    matches more than one document takes the first hit — pass the number when
    it matters which.
    """
    formats = _formats(formats + (("json",) if as_json else ()))
    store = Store(save_dir) if save_dir else None
    errors = 0
    for query in queries:
        number = _resolve_policy_number(query)
        paths = [store.doc_path("policy", number, f) for f in formats] if store else []
        if store and not force and all(p.exists() for p in paths):
            status(f"[skip] policy {number}", "dim")
            continue
        try:
            data = policy.fetch_document(number)
        except Exception as exc:  # noqa: BLE001 - report and continue
            errors += 1
            status(f"[error] policy {query}: {exc}", "red")
            continue
        scraped_at = now_iso()
        renders = {"md": lambda: policy.document_to_markdown(data, scraped_at),
                   "json": lambda: rows_to_json([data])}
        if store:
            for fmt, path in zip(formats, paths):
                store.write(path, renders[fmt]())
                status(f"→ {path}", "green")
            store.log(None, f"policy/{number} — {data['url']}")
        else:
            for fmt in formats:
                emit(renders[fmt](), fmt, plain)
    sys.exit(1 if errors else 0)


@policy_group.command("search", short_help="Keyword search of the Policy Library.")
@click.argument("term")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_plain_option
def policy_search(term, formats, plain):
    """Search the Policy Library for TERM.

    The library returns only the first five hits of each document type and says
    how many there were; when a type is truncated, `policy list --type` has the
    rest.
    """
    formats = _formats(formats)
    rows, url = policy.search(term)
    if not rows:
        _fail(f"nothing in the Policy Library matches {term!r}")
    truncated = {r["group"]: r["group_total"] for r in rows
                 if r["group_total"] > sum(1 for x in rows if x["group"] == r["group"])}
    for group, total in truncated.items():
        status(f"[truncated] {group}: showing 5 of {total}; "
               f"`policy list --type {policy.doc_type_of(group)}` for all of them", "yellow")
    fields = ["number", "title", "group", "contact_area", "url"]
    renders = {
        "md": lambda: policy.listing_to_markdown(
            [dict(r, doc_type=r["group"], topic="") for r in rows],
            f"Policy Library search: {term}", url, now_iso()),
        "csv": lambda: rows_to_csv(rows, fields),
        "json": lambda: rows_to_json(rows),
    }
    for fmt in formats:
        emit(renders[fmt](), fmt, plain)


@policy_group.command("list", short_help="List documents in the Policy Library.")
@click.option("--type", "doc_type", type=click.Choice(POLICY_DOC_TYPES, case_sensitive=False),
              help="Only this document type. Default: every document in the library.")
@click.option("--topic", help='Only this topic, e.g. "Students".')
@click.option("--subtopic", help="Only this subtopic (needs --topic).")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_save_option
@_plain_option
def policy_list(doc_type, topic, subtopic, formats, save_dir, plain):
    """List Policy Library documents, optionally narrowed by type or topic.

    With no filter this is the library's whole A-Z index — every document it
    publishes, with its number, so anything here can be fetched by `policy get`.
    """
    formats = _formats(formats)
    if doc_type or topic or subtopic:
        doc_type = doc_type.capitalize() if doc_type else None
        rows, url = policy.fetch_view_all(doc_type, topic, subtopic)
        heading = " ".join(filter(None, ["Policy Library:", doc_type, topic, subtopic]))
    else:
        rows, url = policy.fetch_index(), policy.TITLE_INDEX_URL
        heading = "Policy Library: all documents"
    if not rows:
        # Topic and subtopic have to match the library's own spelling exactly,
        # including the ampersands: "Buildings & Grounds", "Access & Use".
        _fail(f"no documents matched. Asked: {url}")
    scraped_at = now_iso()
    fields = ["number", "title", "doc_type", "topic", "audience", "contact_area", "url"]
    renders = {
        "md": lambda: policy.listing_to_markdown(rows, heading, url, scraped_at),
        "csv": lambda: rows_to_csv(rows, fields),
        "json": lambda: rows_to_json(rows),
    }
    if not save_dir:
        for fmt in formats:
            emit(renders[fmt](), fmt, plain)
        return
    store = Store(save_dir)
    name = "index" if not (doc_type or topic or subtopic) else \
        "-".join(filter(None, [doc_type, topic, subtopic])).replace(" ", "")
    for fmt in formats:
        path = store.write(store.doc_path("policy", name, fmt), renders[fmt]())
        status(f"→ {path}  ({len(rows)} documents)", "green")
    store.log(None, f"policy/{name} — {url}, {len(rows)} documents")


# ---- legislation -------------------------------------------------------------


@cli.group("legislation", short_help="University legislation: Acts, Statutes, Rules, Orders.")
def legislation_group():
    """Read University legislation, from ANU's index and the Federal Register.

    ANU's Statutes, Rules and Orders are federal law and are registered on the
    Federal Register of Legislation, which is where their status and text come
    from. ANU's own index says which titles apply to the University.

    \b
    Examples:
      anu-pandc legislation list
      anu-pandc legislation get "Coursework Awards Rule"
      anu-pandc legislation get F2024L00724
      anu-pandc legislation search "Academic Integrity"
    """


@legislation_group.command("get", short_help="Fetch an instrument's text and status.")
@click.argument("queries", metavar="ID-OR-NAME...", nargs=-1, required=True)
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(ITEM_FORMATS))
@click.option("--json", "as_json", is_flag=True, help="Shorthand for --format json.")
@click.option("--include-repealed", is_flag=True,
              help="Let a name match something no longer in force.")
@_save_option
@_force_option
@_plain_option
def legislation_get(queries, formats, as_json, include_repealed, save_dir, force, plain):
    """Fetch legislation by Register id (F2024L01752) or by name.

    A name matches every version the Register holds of an instrument, including
    the superseded ones, so the in-force principal version is preferred unless
    --include-repealed says otherwise.
    """
    formats = _formats(formats + (("json",) if as_json else ()))
    store = Store(save_dir) if save_dir else None
    errors = 0
    for query in queries:
        try:
            title_id = legislation.resolve(query, in_force_only=not include_repealed)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            status(f"[error] legislation {query}: {exc}", "red")
            continue
        paths = [store.doc_path("legislation", title_id, f) for f in formats] if store else []
        if store and not force and all(p.exists() for p in paths):
            status(f"[skip] legislation {title_id}", "dim")
            continue
        try:
            data = legislation.fetch_instrument(title_id)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            status(f"[error] legislation {title_id}: {exc}", "red")
            continue
        if not data.get("in_force"):
            status(f"[note] {title_id} is {data.get('status', 'not in force')}", "yellow")
        scraped_at = now_iso()
        renders = {"md": lambda: legislation.instrument_to_markdown(data, scraped_at),
                   "json": lambda: rows_to_json([data])}
        if store:
            for fmt, path in zip(formats, paths):
                store.write(path, renders[fmt]())
                status(f"→ {path}", "green")
            store.log(None, f"legislation/{title_id} — {data['url']}")
        else:
            for fmt in formats:
                emit(renders[fmt](), fmt, plain)
    sys.exit(1 if errors else 0)


@legislation_group.command("list", short_help="ANU's index of University legislation.")
@click.option("--section", help='Only one section: Acts, Statutes, Rules, Orders.')
@click.option("--resolve", "resolve_ids", is_flag=True,
              help="Also look up each item's Register id and status (one request each).")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_save_option
@_plain_option
def legislation_list(section, resolve_ids, formats, save_dir, plain):
    """List the legislation ANU publishes as applying to the University.

    The index page carries names and links but no Register ids, so --resolve
    fetches each item's page to find its id and then its status. That is one
    request per item; without it the list is names and links only.
    """
    formats = _formats(formats)
    rows = legislation.fetch_anu_index()
    if section:
        rows = [r for r in rows if section.lower() in r["section"].lower()]
    if not rows:
        _fail("nothing on the ANU legislation index matched")
    if resolve_ids:
        for row in rows:
            try:
                row["id"] = legislation.resolve_from_anu_page(row["anu_url"])
                if row["id"]:
                    found = legislation.summary(row["id"])
                    row.update({k: found[k] for k in
                                ("kind", "status", "in_force", "made", "url")})
            except Exception as exc:  # noqa: BLE001
                status(f"[error] {row['name']}: {exc}", "red")
    scraped_at = now_iso()
    fields = ["section", "name", "id", "kind", "status", "made", "anu_url", "url"]
    renders = {
        "md": lambda: legislation.index_to_markdown(rows, scraped_at),
        "csv": lambda: rows_to_csv(rows, fields),
        "json": lambda: rows_to_json(rows),
    }
    if not save_dir:
        for fmt in formats:
            emit(renders[fmt](), fmt, plain)
        return
    store = Store(save_dir)
    for fmt in formats:
        path = store.write(store.doc_path("legislation", "index", fmt), renders[fmt]())
        status(f"→ {path}  ({len(rows)} items)", "green")
    store.log(None, f"legislation/index — {legislation.ANU_INDEX_URL}, {len(rows)} items")


@legislation_group.command("search", short_help="Find titles on the Federal Register by name.")
@click.argument("term")
@click.option("--include-repealed", is_flag=True, help="Include titles no longer in force.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_plain_option
def legislation_search(term, include_repealed, formats, plain):
    """Search the Federal Register of Legislation for TERM.

    This matches the *name* of a title. The Register's full-text search is not
    available over its API, so a phrase that appears inside an instrument but
    not in its name will not be found here.
    """
    formats = _formats(formats)
    titles = legislation.search_titles(term, in_force_only=not include_repealed)
    if not titles:
        _fail(f"no titles on the Federal Register match {term!r}")
    rows = legislation.rows(titles)
    renders = {
        "md": lambda: legislation.titles_to_markdown(rows, f"Legislation: {term}", now_iso()),
        "csv": lambda: rows_to_csv(rows, legislation.FIELDS),
        "json": lambda: rows_to_json(rows),
    }
    for fmt in formats:
        emit(renders[fmt](), fmt, plain)


# ---- timetable ---------------------------------------------------------------


@cli.command("timetable", short_help="Scheduled classes from MyTimetable.")
@click.argument("terms", metavar="TERM...", nargs=-1, required=True)
@_year_option
@click.option("--period", "-p", help='Only this teaching period, e.g. "Second Semester".')
@click.option("--include-clones", is_flag=True,
              help="Keep the duplicate 'Clone' activities the publisher emits.")
@click.option("--format", "-f", "formats", multiple=True, type=click.Choice(TABLE_FORMATS))
@_save_option
@_force_option
@_plain_option
def timetable_cmd(terms, year, period, include_clones, formats, save_dir, force, plain):
    """Scheduled classes for a course code (or any search TERM) in a year.

    Reads the Allocate+ Web Publisher behind mytimetable.anu.edu.au. It runs
    one instance per parity of the year, so only the two years those instances
    hold can be asked about — currently 2025 and 2026.

    This is the scheduled timetable and it changes; it is not evidence of what
    was delivered, and it does not say who taught. The Markdown output also
    totals the contact hours one student carries, counting one stream per
    activity group rather than all the alternatives.
    """
    formats = _formats(formats)
    store = Store(save_dir) if save_dir else None
    errors = 0
    for term in terms:
        term = term.upper() if len(term) == 8 and term[:4].isalpha() else term
        paths = [store.table_path(year, "timetable", term, f) for f in formats] if store else []
        if store and not force and all(p.exists() for p in paths):
            status(f"[skip] timetable {term} {year}", "dim")
            continue
        try:
            payload = timetable.fetch_subjects(term, year)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            status(f"[error] timetable {term}: {exc}", "red")
            continue
        rows = timetable.activities(payload, period=period, include_clones=include_clones)
        if not rows:
            status(f"[none] no scheduled activities for {term} in {year}"
                   f"{' (' + period + ')' if period else ''}", "yellow")
            continue
        scraped_at = now_iso()
        table = timetable.rows_for_table(rows)
        renders = {
            "md": lambda: timetable.to_markdown(rows, term, year, scraped_at),
            "csv": lambda: rows_to_csv(table, timetable.FIELDS),
            "json": lambda: rows_to_json(rows),
        }
        if store:
            for fmt, path in zip(formats, paths):
                store.write(path, renders[fmt]())
                status(f"→ {path}  ({len(rows)} activities)", "green")
            store.log(year, f"timetable-{term} — {timetable.rest_url(year, 'subjects')}")
        else:
            for fmt in formats:
                emit(renders[fmt](), fmt, plain)
    sys.exit(1 if errors else 0)


# ---- url ---------------------------------------------------------------------


@cli.command(short_help="Print the P&C URL for each code.")
@click.argument("codes_", metavar="CODE...", nargs=-1, required=True)
@_year_option
@click.option("--kind", type=click.Choice(["program", "subplan", "course"]))
def url(codes_, year, kind):
    """Print the Programs & Courses URL for each CODE (no fetching)."""
    for code in codes_:
        click.echo(codes.url_for(code, year, kind))


if __name__ == "__main__":
    cli()

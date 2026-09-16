"""The on-disk tree that ``--save DIR`` writes.

::

    DIR/<year>/programs/<CODE>.md          one file per program
    DIR/<year>/subplans/<CODE>.md          majors, minors, specialisations
    DIR/<year>/courses/<CODE>.md           one file per course
    DIR/<year>/classes/<CODE>-<Period>-<N>.md
    DIR/<year>/catalogue-<PREFIX>.md       every course under a subject prefix
    DIR/<year>/offerings-<PREFIX>.csv      planned sittings, by offering year
    DIR/<year>/course-codes.txt            union of course codes seen so far
    DIR/<year>/scrape-log.md               append-only log of what was fetched

JSON output uses the same paths with a ``.json`` extension. The layout is
deliberately flat and greppable: a year of a school's curriculum is a few
hundred small Markdown files.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

KIND_DIRS = {"program": "programs", "subplan": "subplans", "course": "courses", "class": "classes"}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def period_slug(period: str) -> str:
    """Filesystem-safe period: 'First Semester' -> 'FirstSemester'."""
    return re.sub(r"[^A-Za-z0-9]", "", period)


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    # ---- paths ---------------------------------------------------------------

    def year_dir(self, year: str) -> Path:
        return self.root / str(year)

    def item_path(self, year: str, kind: str, code: str, fmt: str = "md") -> Path:
        return self.year_dir(year) / KIND_DIRS[kind] / f"{code}.{fmt}"

    def class_path(self, year: str, code: str, period: str, class_number: str, fmt: str = "md") -> Path:
        name = f"{code}-{period_slug(period)}-{class_number}.{fmt}"
        return self.year_dir(year) / "classes" / name

    def table_path(self, year: str, name: str, prefix: str, fmt: str) -> Path:
        return self.year_dir(year) / f"{name}-{prefix}.{fmt}"

    def codes_path(self, year: str) -> Path:
        return self.year_dir(year) / "course-codes.txt"

    def log_path(self, year: str) -> Path:
        return self.year_dir(year) / "scrape-log.md"

    # ---- writing -------------------------------------------------------------

    def write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def log(self, year: str, entry: str) -> None:
        path = self.log_path(year)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"- {now_iso()} {entry}\n")

    # ---- course-code ledger --------------------------------------------------

    def read_codes(self, year: str) -> set[str]:
        path = self.codes_path(year)
        if not path.exists():
            return set()
        return {c.strip() for c in path.read_text(encoding="utf-8").splitlines() if c.strip()}

    def merge_codes(self, year: str, codes: set[str]) -> tuple[int, int]:
        """Union ``codes`` into course-codes.txt. Returns (new, total)."""
        existing = self.read_codes(year)
        merged = existing | set(codes)
        self.write(self.codes_path(year), "\n".join(sorted(merged)) + "\n")
        return len(merged - existing), len(merged)

    # ---- reading back --------------------------------------------------------

    def course_files(self, year: str, fmt: str = "md") -> list[Path]:
        d = self.year_dir(year) / "courses"
        return sorted(d.glob(f"*.{fmt}")) if d.exists() else []

    def class_files(self, year: str | None = None, fmt: str = "md") -> list[Path]:
        years = [self.year_dir(year)] if year else sorted(self.root.glob("[12][0-9][0-9][0-9]"))
        files: list[Path] = []
        for y in years:
            d = y / "classes"
            if d.exists():
                files.extend(sorted(d.glob(f"*.{fmt}")))
        return files

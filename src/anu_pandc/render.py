"""Turn results into text for the terminal or a file."""
from __future__ import annotations

import csv
import io
import json
import sys

from rich.console import Console
from rich.markdown import Markdown
from rich.markup import escape

# Status and progress go to stderr so stdout stays clean for piping.
err = Console(stderr=True, highlight=False, soft_wrap=True)
out = Console()


def status(text: str, style: str | None = None) -> None:
    """One progress/status line on stderr. Text is literal, never rich markup."""
    err.print(escape(text), style=style)


def rows_to_csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    # csv defaults to CRLF, which git normalises on every commit.
    writer = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def rows_to_json(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def emit(text: str, fmt: str, plain: bool = False) -> None:
    """Print ``text`` to stdout. Markdown is rendered with rich on a TTY."""
    if fmt == "md" and not plain and sys.stdout.isatty():
        out.print(Markdown(text))
    else:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")

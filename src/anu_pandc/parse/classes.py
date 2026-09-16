"""Parse ANU class summary pages into structured data and markdown.

A class summary describes a single offered class (e.g. COMP1100, First
Semester 2026, class number 3695). It is richer than the year-agnostic
course definition: real assessment items with weights, due dates, LOs,
plus an Examination(s) section, class schedule, and convener info.

URL pattern: /course/{CODE}/{Period}/{ClassNumber}
e.g. /course/COMP1100/First%20Semester/3695
"""
import re
from bs4 import BeautifulSoup, NavigableString, Tag


# ---- helpers -----------------------------------------------------------------


def _h1_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1", class_="intro__degree-title")
    if not h1:
        return ""
    span = h1.find("span", class_="intro__degree-title__component")
    if span:
        return span.get_text(strip=True)
    return h1.get_text(strip=True)


def _summary_pair(li: Tag) -> tuple[str, str]:
    """Return (label, value) from a degree-summary__code li with text+value spans."""
    label_el = li.find("span", class_="class-summary__code-text")
    value_el = li.find("span", class_="class-summary__code-value")
    label = label_el.get_text(strip=True) if label_el else ""
    value = value_el.get_text(strip=True) if value_el else ""
    return label, value


def _extract_summary_codes(soup: BeautifulSoup) -> dict:
    """Walk degree-summary__code li elements and pull out structured fields.

    The page renders the same code list twice (mobile + desktop). We dedupe
    by label.
    """
    out: dict[str, str | list[str]] = {}
    convener: list[str] = []
    lecturer: list[str] = []

    for li in soup.find_all("li", class_="degree-summary__code"):
        heading = li.find("span", class_="degree-summary__code-heading")
        if heading:
            heading_text = heading.get_text(strip=True).upper()
            if "COURSE CONVENER" in heading_text:
                for sub in li.select("ul li span.class-summary__code-value"):
                    name = sub.get_text(strip=True)
                    if name and name not in convener:
                        convener.append(name)
                continue
            if "LECTURER" in heading_text:
                for sub in li.select("ul li span.class-summary__code-value"):
                    name = sub.get_text(strip=True)
                    if name and name not in lecturer:
                        lecturer.append(name)
                continue
            # Section heading without a key/value pair
            continue

        label, value = _summary_pair(li)
        if label and value and label not in out:
            out[label] = value

    if convener:
        out["Course Convener"] = convener
    if lecturer:
        out["Lecturer"] = lecturer
    return out


def _section_after(soup: BeautifulSoup, h2_id: str) -> Tag | None:
    """Return the <h2> tag with the given id, or None."""
    return soup.find("h2", id=h2_id)


_BLOCK_TAGS = {"p", "li", "blockquote", "div", "ul", "ol", "h3", "h4", "h5", "h6", "tr", "br"}


def _section_text(soup: BeautifulSoup, h2_id: str) -> str:
    """Return joined plain text of the section starting at h2#h2_id, until next h2.

    Walks forward in *document order* (not just sibling order) and stops at the
    next ``<h2>`` anywhere in the tree. ANU class pages occasionally contain
    malformed markup — e.g. ``<b>Timetable webpage.<b></b>`` leaves a ``<b>``
    unclosed, so html.parser nests every later section (Assessment Summary,
    Policies, …) inside it. A sibling-only scan would then slurp that whole
    blob into "Tutorial Registration". Walking document order and breaking at
    the next ``<h2>`` keeps the section to its real content. Tables are skipped
    (dedicated parsers handle them); paragraph-ish breaks are preserved.
    """
    h2 = _section_after(soup, h2_id)
    if not h2:
        return ""
    stop = h2.find_next("h2")

    parts: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            text = " ".join(buf).strip()
            if text:
                parts.append(text)
            buf.clear()

    for el in h2.next_elements:
        if el is stop:
            break
        if isinstance(el, NavigableString):
            parent = el.parent
            if parent is not None and parent.name in ("h2", "script", "style"):
                continue
            if el.find_parent("table") is not None:
                continue
            text = re.sub(r"\s+", " ", str(el)).strip()
            if text:
                buf.append(text)
        elif isinstance(el, Tag) and el.name in _BLOCK_TAGS:
            flush()
    flush()
    return "\n\n".join(parts).strip()


def _description(soup: BeautifulSoup) -> str:
    """The overview blurb sits inside #overview before the first h2."""
    overview = soup.find("div", id="overview")
    if not overview:
        return ""
    parts: list[str] = []
    for child in overview.find_all(recursive=True):
        if child.name == "h2":
            break
        if child.name == "p":
            text = child.get_text(" ", strip=True)
            if text:
                parts.append(text)
    return "\n\n".join(parts).strip()


def _learning_outcomes(soup: BeautifulSoup) -> list[str]:
    """The first <h2> with text 'Learning Outcomes' is followed by an <ol>."""
    for h2 in soup.find_all("h2"):
        if "Learning Outcomes" in h2.get_text(strip=True):
            ol = h2.find_next_sibling("ol")
            if ol:
                return [li.get_text(" ", strip=True) for li in ol.find_all("li")]
    return []


# ---- assessment summary ------------------------------------------------------


_TYPE_CODE_RE = re.compile(r"\(([A-Za-z][A-Za-z0-9]*)\)\s*$")


def _extract_type_code(task_name: str) -> str:
    """Extract the parenthesised type code from a task name.

    Examples:
        'Final Exam (E)' -> 'E'
        'Programming Assignment 1 (A1)' -> 'A1'
        'Mid-Term Test (M)' -> 'M'
        'Participation (P)' -> 'P'
        'Some Task' -> ''
    """
    m = _TYPE_CODE_RE.search(task_name)
    return m.group(1) if m else ""


def _header_index(table: Tag) -> dict[str, int]:
    """Map normalised header labels to column index for the assessment table.

    The assessment summary table has 4 or 5 columns depending on whether the
    course publishes a "Return of assessment" date:
        Assessment task | Value | Due Date | [Return of assessment |] Learning Outcomes
    We key off the header text rather than fixed positions so the optional
    column doesn't shift Learning Outcomes onto the wrong field.
    """
    head = table.find("tr")
    if not head:
        return {}
    cells = head.find_all(["th", "td"])
    out: dict[str, int] = {}
    for i, c in enumerate(cells):
        label = c.get_text(" ", strip=True).lower()
        if "task" in label or label.startswith("assessment"):
            out["task"] = i
        elif "value" in label or "weight" in label:
            out["weight"] = i
        elif "return" in label:
            out["return_date"] = i
        elif "due" in label:
            out["due_date"] = i
        elif "learning outcome" in label or label in ("los", "lo"):
            out["learning_outcomes"] = i
    return out


def _assessment_summary(soup: BeautifulSoup) -> list[dict]:
    h2 = _section_after(soup, "assessment-summary")
    if not h2:
        return []
    table = h2.find_next_sibling("table")
    if not table:
        return []

    cols = _header_index(table)
    # Fall back to fixed positions if the header couldn't be read.
    if not cols:
        cols = {"task": 0, "weight": 1, "due_date": 2, "learning_outcomes": 3}

    def cell(tds, key):
        i = cols.get(key)
        if i is None or i >= len(tds):
            return ""
        return tds[i].get_text(" ", strip=True)

    items = []
    for row in table.find_all("tr"):
        tds = row.find_all("td")
        if len(tds) < 2:
            continue
        task = cell(tds, "task")
        items.append({
            "task": task,
            "type_code": _extract_type_code(task),
            "weight": cell(tds, "weight"),
            "due_date": cell(tds, "due_date"),
            "return_date": cell(tds, "return_date"),
            "learning_outcomes": cell(tds, "learning_outcomes"),
        })
    return items


# ---- per-task assessment details ---------------------------------------------


def _assessment_tasks(soup: BeautifulSoup) -> list[dict]:
    """Each task is rendered as h2#assessmenttask-N + callout box + description."""
    tasks = []
    for h2 in soup.find_all("h2", id=re.compile(r"^assessmenttask-\d+$")):
        n_match = re.search(r"(\d+)$", h2.get("id", ""))
        n = int(n_match.group(1)) if n_match else 0

        callout = h2.find_next_sibling(class_="callout-box")
        value = ""
        due = ""
        return_date = ""
        los = ""
        if callout:
            text = callout.get_text(" ", strip=True)
            value_m = re.search(r"Value:\s*([^A-Za-z]*?\d[\d.]*\s*%)", text)
            if value_m:
                value = value_m.group(1).strip()
            due_m = re.search(r"Due Date:\s*([^A-Za-z]*?\d{1,2}/\d{1,2}/\d{4})", text)
            if due_m:
                due = due_m.group(1).strip()
            ret_m = re.search(r"Return of Assessment:\s*([^A-Za-z]*?\d{1,2}/\d{1,2}/\d{4})", text)
            if ret_m:
                return_date = ret_m.group(1).strip()
            los_m = re.search(r"Learning Outcomes:\s*([\d,\s]+)", text)
            if los_m:
                los = los_m.group(1).strip()

        # The task name is in a <p><b>...</b></p> immediately after the callout
        name = ""
        description_parts: list[str] = []
        cursor = callout if callout else h2
        for sib in cursor.next_siblings:
            if isinstance(sib, Tag):
                if sib.name == "h2":
                    break
                if sib.name == "p":
                    bold = sib.find("b")
                    if bold and not name:
                        name = bold.get_text(" ", strip=True)
                        # Any extra text in the same <p> after the bold name
                        rest = sib.get_text(" ", strip=True)
                        if rest != name:
                            description_parts.append(rest.replace(name, "", 1).strip(" -—:"))
                    else:
                        text = sib.get_text(" ", strip=True)
                        if text:
                            description_parts.append(text)

        tasks.append({
            "n": n,
            "name": name,
            "type_code": _extract_type_code(name),
            "value": value,
            "due_date": due,
            "return_date": return_date,
            "learning_outcomes": los,
            "description": "\n\n".join(p for p in description_parts if p).strip(),
        })
    return tasks


# ---- class schedule ----------------------------------------------------------


def _class_schedule(soup: BeautifulSoup) -> list[dict]:
    h2 = _section_after(soup, "class-schedule")
    if not h2:
        return []
    table = h2.find_next_sibling("table")
    if not table:
        return []
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        rows.append({
            "week": tds[0].get_text(" ", strip=True),
            "summary": tds[1].get_text(" ", strip=True),
            "assessment": tds[2].get_text(" ", strip=True) if len(tds) > 2 else "",
        })
    return rows


# ---- top-level parse ---------------------------------------------------------


def parse_class(soup: BeautifulSoup, code: str, period: str, class_number: str, url: str) -> dict:
    """Parse an ANU class summary page into a structured dict."""
    title = _h1_title(soup)
    summary_codes = _extract_summary_codes(soup)

    return {
        "code": code,
        "period": period,
        "class_number": class_number,
        "url": url,
        "title": title,
        "units": summary_codes.get("Unit Value", ""),
        "mode": summary_codes.get("Mode of Delivery", ""),
        "convener": summary_codes.get("Course Convener", []),
        "lecturer": summary_codes.get("Lecturer", []),
        "class_start_date": summary_codes.get("Class Start Date", ""),
        "class_end_date": summary_codes.get("Class End Date", ""),
        "census_date": summary_codes.get("Census Date", ""),
        "last_enrol_date": summary_codes.get("Last Date to Enrol", ""),
        "description": _description(soup),
        "learning_outcomes": _learning_outcomes(soup),
        "research_led_teaching": _section_text(soup, "research-led-teaching"),
        "recommended_resources": _section_text(soup, "recommended-resources")
            or _section_text(soup, "required-resources"),
        "other_information": _section_text(soup, "other-information"),
        "tutorial_registration": _section_text(soup, "tutorial-registration"),
        "class_schedule": _class_schedule(soup),
        "assessment_summary": _assessment_summary(soup),
        "assessment_tasks": _assessment_tasks(soup),
        "examinations": _section_text(soup, "examination"),
        "participation": _section_text(soup, "participation"),
        "late_submission": _section_text(soup, "latesubmission"),
        "extensions_and_penalties": _section_text(soup, "extensions-and-penalties"),
    }


# ---- markdown ----------------------------------------------------------------


def class_to_markdown(data: dict, scraped_at: str) -> str:
    """Render a parsed class dict to markdown."""
    lines: list[str] = []
    code = data.get("code", "")
    title = data.get("title", "")
    period = data.get("period", "")
    class_number = data.get("class_number", "")

    heading = f"# {code} — {title}".rstrip(" —")
    if period:
        heading += f" — {period}"
    if class_number:
        heading += f" (class {class_number})"
    lines.append(heading)
    lines.append("")

    lines.append(f"- **URL:** {data.get('url', '')}")
    lines.append(f"- **Scraped:** {scraped_at}")
    if data.get("units"):
        lines.append(f"- **Units:** {data['units']}")
    if data.get("mode"):
        lines.append(f"- **Mode:** {data['mode']}")
    convener = data.get("convener") or []
    if convener:
        lines.append(f"- **Convener:** {', '.join(convener)}")
    lecturer = data.get("lecturer") or []
    if lecturer:
        lines.append(f"- **Lecturer:** {', '.join(lecturer)}")
    if data.get("class_start_date"):
        lines.append(f"- **Class start:** {data['class_start_date']}")
    if data.get("class_end_date"):
        lines.append(f"- **Class end:** {data['class_end_date']}")
    if data.get("census_date"):
        lines.append(f"- **Census:** {data['census_date']}")
    if data.get("last_enrol_date"):
        lines.append(f"- **Last enrol:** {data['last_enrol_date']}")
    lines.append("")

    if data.get("description"):
        lines.append("## Description")
        lines.append("")
        lines.append(data["description"])
        lines.append("")

    los = data.get("learning_outcomes") or []
    if los:
        lines.append("## Learning Outcomes")
        lines.append("")
        for i, lo in enumerate(los, 1):
            lines.append(f"{i}. {lo}")
        lines.append("")

    summary = data.get("assessment_summary") or []
    if summary:
        lines.append("## Assessment Summary")
        lines.append("")
        has_return = any((item.get("return_date") or "").strip() for item in summary)
        if has_return:
            lines.append("| Task | Type | Weight | Due Date | Return | LOs |")
            lines.append("|------|------|--------|----------|--------|-----|")
            for item in summary:
                lines.append(
                    f"| {item.get('task','')} | {item.get('type_code','')} | "
                    f"{item.get('weight','')} | {item.get('due_date','')} | "
                    f"{item.get('return_date','')} | {item.get('learning_outcomes','')} |"
                )
        else:
            lines.append("| Task | Type | Weight | Due Date | LOs |")
            lines.append("|------|------|--------|----------|-----|")
            for item in summary:
                lines.append(
                    f"| {item.get('task','')} | {item.get('type_code','')} | "
                    f"{item.get('weight','')} | {item.get('due_date','')} | "
                    f"{item.get('learning_outcomes','')} |"
                )
        lines.append("")

    if data.get("examinations"):
        lines.append("## Examination(s)")
        lines.append("")
        lines.append(data["examinations"])
        lines.append("")

    if data.get("participation"):
        lines.append("## Participation")
        lines.append("")
        lines.append(data["participation"])
        lines.append("")

    tasks = data.get("assessment_tasks") or []
    if tasks:
        lines.append("## Assessment Tasks")
        lines.append("")
        for t in tasks:
            head = f"### Task {t['n']}: {t.get('name','')}".rstrip(": ")
            lines.append(head)
            meta_bits = []
            if t.get("type_code"):
                meta_bits.append(f"Type: {t['type_code']}")
            if t.get("value"):
                meta_bits.append(f"Value: {t['value']}")
            if t.get("due_date"):
                meta_bits.append(f"Due: {t['due_date']}")
            if t.get("return_date"):
                meta_bits.append(f"Return: {t['return_date']}")
            if t.get("learning_outcomes"):
                meta_bits.append(f"LOs: {t['learning_outcomes']}")
            if meta_bits:
                lines.append("")
                lines.append(" · ".join(meta_bits))
            if t.get("description"):
                lines.append("")
                lines.append(t["description"])
            lines.append("")

    if data.get("late_submission"):
        lines.append("## Late Submission")
        lines.append("")
        lines.append(data["late_submission"])
        lines.append("")

    if data.get("extensions_and_penalties"):
        lines.append("## Extensions and Penalties")
        lines.append("")
        lines.append(data["extensions_and_penalties"])
        lines.append("")

    schedule = data.get("class_schedule") or []
    if schedule:
        lines.append("## Class Schedule")
        lines.append("")
        lines.append("| Week | Summary | Assessment |")
        lines.append("|------|---------|------------|")
        for r in schedule:
            week = r.get("week", "").replace("|", "\\|")
            summary_text = r.get("summary", "").replace("|", "\\|")
            assessment_text = r.get("assessment", "").replace("|", "\\|")
            lines.append(f"| {week} | {summary_text} | {assessment_text} |")
        lines.append("")

    if data.get("research_led_teaching"):
        lines.append("## Research-Led Teaching")
        lines.append("")
        lines.append(data["research_led_teaching"])
        lines.append("")

    if data.get("recommended_resources"):
        lines.append("## Recommended/Required Resources")
        lines.append("")
        lines.append(data["recommended_resources"])
        lines.append("")

    if data.get("other_information"):
        lines.append("## Other Information")
        lines.append("")
        lines.append(data["other_information"])
        lines.append("")

    if data.get("tutorial_registration"):
        lines.append("## Tutorial Registration")
        lines.append("")
        lines.append(data["tutorial_registration"])
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

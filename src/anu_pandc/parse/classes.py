"""Parse ANU class summary pages into structured data and markdown.

A class summary describes a single offered class (e.g. COMP1100, First
Semester 2026, class number 3695). It is richer than the year-agnostic
course definition: real assessment items with weights, due dates, LOs,
plus an Examination(s) section, class schedule, and convener info.

URL pattern: /course/{CODE}/{Period}/{ClassNumber}
e.g. /course/COMP1100/First%20Semester/3695
"""
import copy
import re

from bs4 import BeautifulSoup, Tag

from anu_pandc.parse.html_md import to_markdown


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


def _section_after(soup: BeautifulSoup, h2_id: str, title: str = "") -> Tag | None:
    """Return the <h2> tag with the given id, or None.

    ``title`` picks between h2s sharing an id: the page gives both "Learning
    Outcomes" and "Policies" ``id="policies"``.
    """
    for h2 in soup.find_all("h2", id=h2_id):
        if not title or h2.get_text(strip=True).startswith(title):
            return h2
    return None


BASE_URL = "https://programsandcourses.anu.edu.au"


def _section_nodes(h2: Tag) -> list:
    """The top-level nodes between ``h2`` and the next ``<h2>``, in document order.

    ANU class pages occasionally contain malformed markup — e.g.
    ``<b>Timetable webpage.<b></b>`` leaves a ``<b>`` unclosed, so html.parser
    nests every later section (Assessment Summary, Policies, …) inside it. A
    sibling-only scan would then slurp that whole blob into "Tutorial
    Registration". Walking document order, stepping *into* any element that
    contains the next ``<h2>`` and stopping at it, keeps the section to its
    real content.
    """
    stop = h2.find_next("h2")
    wraps_stop = {id(p) for p in stop.parents} if stop else set()
    nodes: list = []
    for el in h2.next_elements:
        if el is stop:
            break
        if h2 in el.parents or (nodes and nodes[-1] in el.parents):
            continue
        if id(el) in wraps_stop:
            continue
        nodes.append(el)
    return nodes


def _section_markdown(nodes: list) -> str:
    """Render section nodes as Markdown, keeping links, lists and emphasis."""
    frag = BeautifulSoup("<div></div>", "html.parser").div
    for node in nodes:
        frag.append(copy.copy(node))
    return to_markdown(frag, BASE_URL)


def _section_text(soup: BeautifulSoup, h2_id: str, title: str = "") -> str:
    """Markdown for the section starting at h2#h2_id, up to the next h2.

    Tables are skipped: the two sections that have one (Class Schedule and
    Assessment Summary) have dedicated parsers.
    """
    h2 = _section_after(soup, h2_id, title)
    if not h2:
        return ""
    nodes = [n for n in _section_nodes(h2) if not (isinstance(n, Tag) and n.name == "table")]
    return _section_markdown(nodes)


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
            text = to_markdown(child, BASE_URL)
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

        # The task name is in a <p><b>...</b></p> immediately after the
        # callout; everything after it is the description.
        name = ""
        description_parts: list[str] = []
        rest: list = []
        for node in _section_nodes(h2):
            if node is callout:
                continue
            if not name and isinstance(node, Tag) and node.name == "p" and node.find("b"):
                name = node.find("b").get_text(" ", strip=True)
                # Any extra text in the same <p> after the bold name
                extra = node.get_text(" ", strip=True)
                if extra != name:
                    description_parts.append(extra.replace(name, "", 1).strip(" -—:"))
                continue
            rest.append(node)
        description_parts.append(_section_markdown(rest))

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


# ---- contacts ----------------------------------------------------------------


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+$")


def _contacts(soup: BeautifulSoup) -> list[dict]:
    """The Contacts tab: one callout box per convener or instructor.

    Each box has a Details pane (name, then phone and/or email, then research
    interests) and a Consulting Hours pane (a small table of free-text rows).
    """
    contacts = []
    for h2 in soup.find_all("h2", id=re.compile(r"^contact_")):
        box = h2.find_parent(class_="callout-box")
        if box is None:
            continue
        role = h2.get_text(strip=True)
        for details in box.find_all(id=re.compile(r"^contact_details_")):
            entry = {"role": role, "name": "", "phone": "", "email": "",
                     "research_interests": "", "consulting_hours": []}
            inner = details.select_one("table.class-contact-table table")
            lines = [td.get_text(" ", strip=True) for td in inner.find_all("td")] if inner else []
            lines = [line for line in lines if line]
            if lines:
                entry["name"] = lines[0]
            for line in lines[1:]:
                if _EMAIL_RE.match(line):
                    entry["email"] = entry["email"] or line
                elif not entry["phone"]:
                    entry["phone"] = line
            interests = details.find("h3", string=re.compile("Research Interests"))
            if interests and interests.parent:
                text = interests.parent.get_text(" ", strip=True)
                entry["research_interests"] = text.replace("Research Interests", "", 1).strip()

            hours_id = details["id"].replace("contact_details_", "contact_consulting_hours_")
            hours = box.find(id=hours_id)
            if hours:
                for tr in hours.select("table.table-consulting-hours tr"):
                    row = " ".join(td.get_text(" ", strip=True) for td in tr.find_all("td"))
                    row = re.sub(r"\s+", " ", row).strip()
                    if row:
                        entry["consulting_hours"].append(row)
            contacts.append(entry)
    return contacts


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
        "required_resources": _section_text(soup, "required-resources"),
        "recommended_resources": _section_text(soup, "recommended-resources"),
        "staff_feedback": _section_text(soup, "staff-feedback"),
        "student_feedback": _section_text(soup, "student-feedback"),
        "other_information": _section_text(soup, "other-information"),
        "tutorial_registration": _section_text(soup, "tutorial-registration"),
        "class_schedule": _class_schedule(soup),
        "assessment_summary": _assessment_summary(soup),
        "policies": _section_text(soup, "policies", "Policies"),
        "assessment_requirements": _section_text(soup, "assessment-requirements"),
        "moderation_of_assessment": _section_text(soup, "moderation-of-assessment"),
        "assessment_tasks": _assessment_tasks(soup),
        "examinations": _section_text(soup, "examination"),
        "participation": _section_text(soup, "participation"),
        "academic_integrity": _section_text(soup, "academic-integrity"),
        "online_submission": _section_text(soup, "onlinesubmission"),
        "hardcopy_submission": _section_text(soup, "hardcopysubmission"),
        "late_submission": _section_text(soup, "latesubmission"),
        "referencing_requirements": _section_text(soup, "referencing-requirements"),
        "returning_assignments": _section_text(soup, "returning-assignments"),
        "extensions_and_penalties": _section_text(soup, "extensions-and-penalties"),
        "resubmission_of_assignments": _section_text(soup, "resubmission-of-assignments"),
        "privacy_notice": _section_text(soup, "privacy-notice"),
        "distribution_of_grades": _section_text(soup, "distribution-of-grades-policy"),
        "support_for_students": _section_text(soup, "support-for-students"),
        "contacts": _contacts(soup),
    }


# ---- markdown ----------------------------------------------------------------


def _sections(lines: list[str], data: dict, pairs: list[tuple[str, str]]) -> None:
    """Append a ``## heading`` and body for each non-empty text field."""
    for key, heading in pairs:
        if data.get(key):
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(data[key])
            lines.append("")


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

    _sections(lines, data, [
        ("assessment_requirements", "Assessment Requirements"),
        ("moderation_of_assessment", "Moderation of Assessment"),
        ("examinations", "Examination(s)"),
        ("participation", "Participation"),
    ])

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

    _sections(lines, data, [
        ("online_submission", "Online Submission"),
        ("hardcopy_submission", "Hardcopy Submission"),
        ("late_submission", "Late Submission"),
        ("returning_assignments", "Returning Assignments"),
        ("extensions_and_penalties", "Extensions and Penalties"),
        ("resubmission_of_assignments", "Resubmission of Assignments"),
        ("referencing_requirements", "Referencing Requirements"),
    ])

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

    _sections(lines, data, [
        ("research_led_teaching", "Research-Led Teaching"),
        ("required_resources", "Required Resources"),
        ("recommended_resources", "Recommended Resources"),
        ("staff_feedback", "Staff Feedback"),
        ("student_feedback", "Student Feedback"),
        ("other_information", "Other Information"),
        ("tutorial_registration", "Tutorial Registration"),
    ])

    contacts = data.get("contacts") or []
    if contacts:
        lines.append("## Contacts")
        lines.append("")
        for c in contacts:
            bits = [f"**{c.get('role', '')}:** {c.get('name', '')}"]
            if c.get("email"):
                bits.append(c["email"])
            if c.get("phone"):
                bits.append(c["phone"])
            lines.append("- " + " · ".join(bits))
            if c.get("consulting_hours"):
                lines.append(f"  - Consulting hours: {'; '.join(c['consulting_hours'])}")
            if c.get("research_interests"):
                lines.append(f"  - Research interests: {c['research_interests']}")
        lines.append("")

    # University-wide text, the same on every class summary.
    _sections(lines, data, [
        ("academic_integrity", "Academic Integrity"),
        ("policies", "Policies"),
        ("privacy_notice", "Privacy Notice"),
        ("distribution_of_grades", "Distribution of Grades Policy"),
        ("support_for_students", "Support for Students"),
    ])

    return "\n".join(lines).rstrip() + "\n"

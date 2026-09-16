"""Parse ANU course pages into structured data and markdown."""
import re
from bs4 import BeautifulSoup


def _get_title(soup: BeautifulSoup) -> str:
    """Extract the course title from h1.intro__degree-title."""
    h1 = soup.find("h1", class_="intro__degree-title")
    if h1:
        return h1.get_text(strip=True)
    return ""


def _get_units(soup: BeautifulSoup) -> str:
    """Extract the unit value as a string (e.g. '6')."""
    # Primary: student-contribution-band dl — find the 'Unit value:' dt and its dd
    dl = soup.find("dl", class_="student-contribution-band")
    if dl:
        for dt in dl.find_all("dt"):
            if "unit value" in dt.get_text(strip=True).lower():
                dd = dt.find_next_sibling("dd")
                if dd:
                    m = re.search(r"(\d+)", dd.get_text(strip=True))
                    if m:
                        return m.group(1)
    # Fallback: degree-summary units li
    li = soup.find("li", class_="degree-summary__requirements-units")
    if li:
        m = re.search(r"(\d+)\s*unit", li.get_text(strip=True), re.IGNORECASE)
        if m:
            return m.group(1)
    return ""


def _get_level(code: str) -> str:
    """Derive the level from the course code (e.g. COMP1730 -> '1000')."""
    m = re.search(r"[A-Z]{2,4}(\d)", code)
    if m:
        return m.group(1) + "000"
    return ""


def _get_requisites(soup: BeautifulSoup) -> tuple[str, str, str]:
    """Return (prerequisites, incompatibilities, requisite_raw) extracted from div.requisite.

    requisite_raw is the complete unprocessed text of the div, preserved so the
    split heuristics can be audited and improved over time.
    """
    div = soup.find("div", class_="requisite")
    if not div:
        return "None", "None", ""

    full_text = div.get_text(" ", strip=True)
    full_text = " ".join(full_text.splitlines())

    # Split on the incompatibility marker
    prereq_text = "None"
    incompat_text = "None"

    # "To enrol in this course you must" covers all observed variants:
    #   "...must have completed"
    #   "...must have successfully completed or be currently studying"
    #   "...must:" (followed by bullet conditions)
    prereq_markers = ["To enrol in this course you must"]
    incompat_markers = [
        "You are not able to enrol",
        "You cannot enrol",
        "You may not enrol",
        "Incompatible with",
    ]

    # Find where incompatibilities start in the text
    incompat_start = None
    for marker in incompat_markers:
        idx = full_text.find(marker)
        if idx != -1:
            if incompat_start is None or idx < incompat_start:
                incompat_start = idx

    # Find where prerequisites start
    prereq_start = None
    for marker in prereq_markers:
        idx = full_text.find(marker)
        if idx != -1:
            if prereq_start is None or idx < prereq_start:
                prereq_start = idx

    if prereq_start is not None:
        end = incompat_start if incompat_start and incompat_start > prereq_start else len(full_text)
        prereq_text = full_text[prereq_start:end].strip()

    if incompat_start is not None:
        incompat_text = full_text[incompat_start:].strip()

    return prereq_text, incompat_text, full_text


def _extract_prereq_codes(prereq_text: str) -> list[str]:
    """Extract course codes (e.g. COMP1100) mentioned in a prerequisite string."""
    if prereq_text == "None":
        return []
    return re.findall(r'\b[A-Z]{2,4}\d{4}\b', prereq_text)


def _get_cotaught(soup: BeautifulSoup) -> list[str]:
    """Extract co-taught course codes from the degree-summary sidebar.

    Looks for li.degree-summary__code whose heading text is 'Co-taught Course'
    and returns the course codes linked within it.
    """
    codes = []
    for li in soup.find_all("li", class_="degree-summary__code"):
        heading = li.find("span", class_="degree-summary__code-heading")
        if not heading:
            continue
        if "co-taught" not in heading.get_text(strip=True).lower():
            continue
        for a in li.find_all("a"):
            code = a.get_text(strip=True)
            if re.match(r"^[A-Z]{2,4}\d{4}$", code):
                codes.append(code)
    return list(dict.fromkeys(codes))  # deduplicate, preserve order


def _get_offerings(soup: BeautifulSoup) -> list[dict]:
    """Extract future offering information from the #class tab.

    Returns a list of dicts with keys: year, semester, mode, class_number,
    summary_url. summary_url is None when the row shows "N/A" (no live class
    summary page yet — typical for future-year offerings).
    """
    class_tab = soup.find(id="class")
    if not class_tab:
        return []

    tabs_container = class_tab.find(id="tabs-container")
    if not tabs_container:
        return []

    # Build a mapping from content-div id -> year label
    year_map: dict[str, str] = {}
    menu = tabs_container.find("div", class_="course-tabs-menu")
    if menu:
        for a in menu.find_all("a", href=True):
            href = a["href"].lstrip("#")
            year_map[href] = a.get_text(strip=True)

    offerings = []
    for content_div in tabs_container.find_all("div", class_="course-tab-content"):
        div_id = content_div.get("id", "")
        year = year_map.get(div_id, "")

        for h3 in content_div.find_all("h3"):
            semester = h3.get_text(strip=True)
            table = h3.find_next_sibling("table")
            if not table:
                continue
            for row in table.find_all("tr"):
                tds = row.find_all("td")
                # columns: class_number, start, last_enrol, census, end, mode, summary
                if len(tds) < 6:
                    continue
                class_number = tds[0].get_text(strip=True)
                mode = tds[5].get_text(strip=True)
                summary_url = None
                if len(tds) >= 7:
                    a = tds[6].find("a", href=True)
                    if a:
                        summary_url = a["href"]
                offerings.append({
                    "year": year,
                    "semester": semester,
                    "mode": mode,
                    "class_number": class_number,
                    "summary_url": summary_url,
                })

    return offerings


def _get_description(soup: BeautifulSoup) -> str:
    """Extract the course description from div.introduction paragraphs."""
    intro_div = soup.find("div", class_="introduction")
    if intro_div:
        ps = intro_div.find_all("p")
        parts = [p.get_text(strip=True) for p in ps if p.get_text(strip=True)]
        if parts:
            return " ".join(parts)
    return ""


def _get_learning_outcomes(soup: BeautifulSoup) -> list[str]:
    """Extract learning outcomes from the ol after h2 'Learning Outcomes'."""
    h2 = soup.find("h2", string=lambda t: t and "Learning Outcomes" in t)
    if h2:
        ol = h2.find_next_sibling("ol")
        if ol:
            return [li.get_text(strip=True) for li in ol.find_all("li")]
    return []


def _get_assessment(soup: BeautifulSoup) -> list[dict]:
    """
    Extract assessment items from the ol after h2 'Indicative Assessment'.

    Each item looks like:
        "Homework, Assignments and Lab Tests (20) [LO 1,2,3,4,5,6]"
    Returns a list of dicts with keys 'task' (str) and 'weight' (str).
    """
    h2 = soup.find("h2", string=lambda t: t and "Indicative Assessment" in t)
    if not h2:
        return []
    ol = h2.find_next_sibling("ol")
    if not ol:
        return []
    items = []
    for li in ol.find_all("li"):
        text = li.get_text(strip=True)
        # Task name: text before the first '('
        m = re.match(r"^(.*?)\s*\((\d+(?:\.\d+)?)\)", text)
        if m:
            task = m.group(1).strip().rstrip(",").strip()
            weight = m.group(2)
        else:
            task = text
            weight = ""
        items.append({"task": task, "weight": weight})
    return items


def parse_course(soup: BeautifulSoup, code: str, url: str) -> dict:
    """
    Parse an ANU course page into a structured dict.

    Returns keys: code, url, title, units, level, prerequisites,
    incompatibilities, description, learning_outcomes, assessment.
    """
    title = _get_title(soup)
    units = _get_units(soup)
    level = _get_level(code)
    prerequisites, incompatibilities, requisite_raw = _get_requisites(soup)
    prerequisite_codes = _extract_prereq_codes(prerequisites)
    cotaught = _get_cotaught(soup)
    description = _get_description(soup)
    learning_outcomes = _get_learning_outcomes(soup)
    assessment = _get_assessment(soup)
    offerings = _get_offerings(soup)

    return {
        "code": code,
        "url": url,
        "title": title,
        "units": units,
        "level": level,
        "prerequisites": prerequisites,
        "prerequisite_codes": prerequisite_codes,
        "incompatibilities": incompatibilities,
        "requisite_raw": requisite_raw,
        "cotaught": cotaught,
        "description": description,
        "learning_outcomes": learning_outcomes,
        "assessment": assessment,
        "offerings": offerings,
    }


def course_to_markdown(data: dict, scraped_at: str) -> str:
    """
    Render a parsed course dict to markdown.

    The scraped_at parameter is an ISO 8601 timestamp string.
    """
    lines: list[str] = []

    title = data.get("title", "")
    code = data.get("code", "")
    units = data.get("units", "")
    level = data.get("level", "")

    heading = f"# {code}"
    if title:
        heading += f" — {title}"
    suffix_parts = []
    if units:
        suffix_parts.append(f"{units} units")
    if level:
        suffix_parts.append(f"Level {level}")
    if suffix_parts:
        heading += f" ({', '.join(suffix_parts)})"
    lines.append(heading)
    lines.append("")

    lines.append(f"- **URL:** {data.get('url', '')}")
    lines.append(f"- **Scraped:** {scraped_at}")
    lines.append(f"- **Prerequisites:** {data.get('prerequisites', 'None')}")
    prereq_codes = data.get("prerequisite_codes", [])
    if prereq_codes:
        lines.append(f"- **Prerequisite codes:** {', '.join(prereq_codes)}")
    lines.append(f"- **Incompatibilities:** {data.get('incompatibilities', 'None')}")
    requisite_raw = data.get("requisite_raw", "")
    if requisite_raw:
        lines.append(f"- **Requisite raw:** {requisite_raw}")
    cotaught = data.get("cotaught", [])
    if cotaught:
        lines.append(f"- **Co-taught with:** {', '.join(cotaught)}")
    offerings = data.get("offerings", [])
    if offerings:
        # Compact: "2027 First Semester (In Person, class 3695)"
        offering_strs = []
        for o in offerings:
            base = f"{o['year']} {o['semester']}"
            extras = []
            if o.get("mode"):
                extras.append(o["mode"])
            if o.get("class_number"):
                extras.append(f"class {o['class_number']}")
            if extras:
                base += f" ({', '.join(extras)})"
            offering_strs.append(base)
        lines.append(f"- **Offered in:** {'; '.join(offering_strs)}")
    else:
        lines.append("- **Offered in:** No future offerings found")
    lines.append("")

    description = data.get("description", "")
    if description:
        lines.append("## Description")
        lines.append("")
        lines.append(description)
        lines.append("")

    learning_outcomes = data.get("learning_outcomes", [])
    if learning_outcomes:
        lines.append("## Learning Outcomes")
        lines.append("")
        for i, outcome in enumerate(learning_outcomes, 1):
            lines.append(f"{i}. {outcome}")
        lines.append("")

    assessment = data.get("assessment", [])
    if assessment:
        lines.append("## Assessment")
        lines.append("")
        lines.append("| Task | Weight |")
        lines.append("|------|--------|")
        for item in assessment:
            task = item.get("task", "")
            weight = item.get("weight", "")
            weight_str = f"{weight}%" if weight else ""
            lines.append(f"| {task} | {weight_str} |")
        lines.append("")

    return "\n".join(lines)

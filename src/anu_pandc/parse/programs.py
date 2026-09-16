"""Parse ANU program pages into structured data and markdown."""
import re
from bs4 import BeautifulSoup, Tag

# Matches /YYYY/course/COMP1100 style hrefs (any 4-digit year)
_COURSE_HREF_RE = re.compile(r"/\d{4}/course/([A-Z]{2,4}\d{4}[A-Z]?)")

# Matches requirement group headings in various forms:
#   "6 units from completion of..."
#   "A minimum/maximum of 12 units from the following list:"
#   "The 24 units must consist of:"
_HEADING_RE = re.compile(
    r"("
    r"(?:the\s+completion\s+of\s+)?\d+\s+units?\s+from"
    r"|(?:minimum|maximum)\s+of\s+\d+\s+units?\s+from"
    r"|[Tt]he\s+\d+\s+units?\s+must\s+consist"
    r")",
    re.IGNORECASE,
)


def _get_title(soup: BeautifulSoup) -> str:
    """Extract the program title from the page."""
    # Primary selector: h1 with class intro__degree-title
    h1 = soup.find("h1", class_="intro__degree-title")
    if h1:
        # Try to get text from the inner span first
        span = h1.find("span", class_="intro__degree-title__component")
        if span:
            return span.get_text(strip=True)
        return h1.get_text(strip=True)
    # Fallback: bare span
    span = soup.find("span", class_="intro__degree-title__component")
    if span:
        return span.get_text(strip=True)
    return ""


def _get_min_units(soup: BeautifulSoup) -> int | None:
    """Extract minimum units from the degree summary."""
    # Try the degree-summary requirements units li
    li = soup.find("li", class_="degree-summary__requirements-units")
    if li:
        text = li.get_text(strip=True)
        m = re.search(r"(\d+)\s+[Uu]nits?", text)
        if m:
            return int(m.group(1))
    # Fallback: look in p or li elements for "Minimum N units"
    for tag in soup.find_all(["p", "li"]):
        text = tag.get_text(strip=True)
        m = re.search(r"[Mm]inimum\s+(\d+)\s+[Uu]nits?", text)
        if m:
            return int(m.group(1))
    return None


def _content_div(soup: BeautifulSoup) -> Tag | None:
    """Return the main program requirements content div."""
    # The requirements are in div#study > div.body__inner.w-doublewide.copy
    study_div = soup.find("div", id="study")
    if study_div:
        content = study_div.find("div", class_=lambda c: c and "body__inner" in c and "w-doublewide" in c)
        if content:
            return content
    # Fallback: first matching div in whole page
    return soup.find("div", class_=lambda c: c and "body__inner" in c and "w-doublewide" in c)


def _extract_course_from_p(p: Tag) -> list[dict]:
    """Extract course dicts from a <p> tag containing course links."""
    courses = []
    for a in p.find_all("a", href=_COURSE_HREF_RE):
        href = a.get("href", "")
        m = _COURSE_HREF_RE.search(href)
        if not m:
            continue
        code = m.group(1)
        # Title: text of p after the link, stripped of the code itself
        # Full p text: "COMP1100 Programming as Problem Solving (6 units)"
        # Note: when a single <p> contains two course links the title extraction
        # may be imperfect — both codes share the same paragraph text, so the
        # title of each may include text belonging to the other course.
        full_text = p.get_text(" ", strip=True)
        # Units from text like "(6 units)"
        units_m = re.search(r"\((\d+)\s+units?\)", full_text)
        units = int(units_m.group(1)) if units_m else None
        # Title: strip code from front and units from end
        title_text = full_text
        title_text = re.sub(r"^\s*" + re.escape(code) + r"\s*", "", title_text).strip()
        title_text = re.sub(r"\s*\(\d+\s+units?\)\s*$", "", title_text).strip()
        # Remove nbsp characters
        title_text = title_text.replace("\xa0", " ").strip()
        courses.append({"code": code, "title": title_text, "units": units})
    return courses


def _parse_requirements(content: Tag) -> list[dict]:
    """
    Parse requirement groups and descriptive text from the content div.

    Returns a list of blocks:
    - {'type': 'text', 'content': str}
    - {'type': 'group', 'heading': str, 'courses': list[dict]}
    """
    requirements = []
    current_group = None

    def flush():
        nonlocal current_group
        if current_group:
            requirements.append(current_group)
            current_group = None

    for p in content.find_all("p"):
        text = p.get_text(" ", strip=True).replace("\xa0", " ")
        if not text:
            continue

        # Check if this p is a group heading
        if _HEADING_RE.search(text):
            flush()
            current_group = {"type": "group", "heading": text, "courses": []}
            # Some headings also contain course links on the same p
            current_group["courses"].extend(_extract_course_from_p(p))
        else:
            # Collect course links from this p
            courses = _extract_course_from_p(p)
            if courses:
                if current_group:
                    current_group["courses"].extend(courses)
                else:
                    # Courses found before any heading; create a default group
                    current_group = {"type": "group", "heading": "Requirements", "courses": courses}
            else:
                # It's just text. Flush any open group and save as a text block.
                flush()
                requirements.append({"type": "text", "content": text})

    flush()
    return requirements


def _parse_specialisations(content: Tag) -> list[dict]:
    """
    Parse majors/minors/specialisations sections.

    Each section starts with an <h2> like "Majors" or "Minors",
    followed by a div.body__inner__columns containing anchor links.
    """
    specialisations = []
    for h2 in content.find_all("h2"):
        heading_text = h2.get_text(strip=True)
        # Only process headings that look like specialisation types
        if not any(kw in heading_text for kw in ("Major", "Minor", "Specialisation")):
            continue
        items = []
        # Find the next sibling div.body__inner__columns
        sibling = h2.find_next_sibling()
        while sibling:
            if isinstance(sibling, Tag) and sibling.name == "div" and "body__inner__columns" in (sibling.get("class") or []):
                # Each column has <a href="/major/CODE"> or <a href="/minor/CODE">
                for a in sibling.find_all("a", href=True):
                    href = a.get("href", "")
                    # Extract code from last path segment
                    code = href.rstrip("/").split("/")[-1]
                    name = a.get_text(strip=True)
                    if code and name:
                        items.append({"name": name, "code": code})
                break
            # Stop at next h2
            if isinstance(sibling, Tag) and sibling.name == "h2":
                break
            sibling = sibling.find_next_sibling()
        if items:
            specialisations.append({"type": heading_text, "items": items})
    return specialisations


def _get_introduction(soup: BeautifulSoup) -> str:
    """Extract the introduction text from the introduction div.

    Programs use <div class="introduction" id="introduction">; subplans use
    <div id="introduction"> (no class). Falling back to the id selector covers
    both. The first match wins, which on program pages is the overview-tab
    intro rather than the duplicate inside the first-year-advice tab.
    """
    intro_div = soup.find("div", class_="introduction") or soup.find("div", id="introduction")
    if intro_div:
        ps = intro_div.find_all("p")
        parts = [p.get_text(strip=True).replace("\xa0", " ") for p in ps if p.get_text(strip=True)]
        if parts:
            return "\n\n".join(parts)
    return ""


def _get_learning_outcomes(soup: BeautifulSoup) -> list[str]:
    """Extract learning outcomes from the ol after h2#learning-outcomes."""
    h2 = soup.find("h2", id="learning-outcomes")
    if not h2:
        h2 = soup.find("h2", string=lambda t: t and "Learning Outcomes" in t)
    if h2:
        ol = h2.find_next_sibling("ol")
        if ol:
            return [li.get_text(strip=True) for li in ol.find_all("li")]
    return []


def _all_course_codes(soup: BeautifulSoup) -> list[str]:
    """
    Collect all course codes found via /2026/course/ links throughout the page.
    Returns a sorted, deduplicated list.
    """
    codes: set[str] = set()
    for a in soup.find_all("a", href=_COURSE_HREF_RE):
        href = a.get("href", "")
        m = _COURSE_HREF_RE.search(href)
        if m:
            codes.add(m.group(1))
    return sorted(codes)


def parse_program(soup: BeautifulSoup, code: str, url: str) -> dict:
    """
    Parse an ANU program page into a structured dict.

    Returns keys: code, url, title, min_units, requirements, specialisations,
    all_course_codes.
    """
    title = _get_title(soup)
    min_units = _get_min_units(soup)
    introduction = _get_introduction(soup)
    learning_outcomes = _get_learning_outcomes(soup)
    all_codes = _all_course_codes(soup)
    content = _content_div(soup)
    requirements: list[dict] = []
    specialisations: list[dict] = []
    if content:
        requirements = _parse_requirements(content)
        specialisations = _parse_specialisations(content)

    return {
        "code": code,
        "url": url,
        "title": title,
        "min_units": min_units,
        "introduction": introduction,
        "learning_outcomes": learning_outcomes,
        "requirements": requirements,
        "specialisations": specialisations,
        "all_course_codes": all_codes,
    }


def program_to_markdown(data: dict, scraped_at: str, year: str | None = None) -> str:
    """
    Render a parsed program (or subplan) dict to markdown.

    ``scraped_at`` is an ISO 8601 timestamp string. ``year`` is the catalogue
    year shown in the heading; it defaults to the year of ``scraped_at`` for
    backwards compatibility, but callers should pass the catalogue year they
    actually fetched, since a 2027 page can be scraped in 2026.
    """
    year = year or scraped_at[:4]
    lines: list[str] = []

    lines.append(f"# {data['title']} ({data['code']}) {year}")
    lines.append("")
    if data.get("min_units") is not None:
        lines.append(f"- **Total units:** {data['min_units']}")
    lines.append(f"- **URL:** {data['url']}")
    lines.append(f"- **Scraped:** {scraped_at}")
    lines.append("")

    introduction = data.get("introduction", "")
    if introduction:
        lines.append("## Introduction")
        lines.append("")
        lines.append(introduction)
        lines.append("")

    learning_outcomes = data.get("learning_outcomes", [])
    if learning_outcomes:
        lines.append("## Learning Outcomes")
        lines.append("")
        for i, outcome in enumerate(learning_outcomes, 1):
            lines.append(f"{i}. {outcome}")
        lines.append("")

    for req in data.get("requirements", []):
        if req["type"] == "text":
            lines.append(req["content"])
            lines.append("")
        elif req["type"] == "group":
            if not req["courses"]:
                lines.append(f"## {req['heading']}")
                lines.append("")
            else:
                lines.append(f"## {req['heading']}")
                lines.append("")
                lines.append("| Code | Title | Units |")
                lines.append("|------|-------|-------|")
                for course in req["courses"]:
                    code = course.get("code", "")
                    title = course.get("title", "")
                    units = course.get("units")
                    lines.append(f"| {code} | {title} | {units if units is not None else ''} |")
                lines.append("")

    for spec in data.get("specialisations", []):
        lines.append(f"## {spec['type']}")
        lines.append("")
        for item in spec["items"]:
            lines.append(f"- {item['name']} ({item['code']})")
        lines.append("")

    return "\n".join(lines)

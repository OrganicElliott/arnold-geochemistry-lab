"""Write the publication lists into the site from data/publications.bib.

Fills in the text between these markers (everything else is left alone):
    publications.html   <!-- BEGIN publications -->        ... <!-- END publications -->
    index.html          <!-- BEGIN recent-publications --> ... <!-- END recent-publications -->

Run after editing the .bib file:

    python scripts/build_publications.py
"""
import html
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BIB = ROOT / "data" / "publications.bib"
MEMBERS = ROOT / "data" / "lab-members.txt"
RECENT_COUNT = 5

# Sections of the Publications page, in order, and the BibTeX types in each.
# Only the first section feeds "Recent publications" on the homepage.
SECTIONS = [
    ("articles", "Journal articles and book chapters", {"article", "incollection", "inbook", "book"}),
    ("abstracts", "Conference abstracts", {"inproceedings", "conference", "proceedings"}),
    ("theses", "Theses", {"phdthesis", "mastersthesis"}),
]
THESIS_LABEL = {"phdthesis": "Ph.D. dissertation", "mastersthesis": "M.S. thesis"}

# Common LaTeX accents found in Google Scholar exports -> combining characters.
ACCENTS = {"'": "́", "`": "̀", "^": "̂", '"': "̈",
           "~": "̃", "c": "̧", "v": "̌"}


# ---------- reading the .bib file ----------

def parse_bib(text: str) -> list[dict]:
    """Return one dict of fields per @entry, in file order. The entry type is in '_type'."""
    entries = []
    for match in re.finditer(r"@(\w+)\s*\{", text):
        kind = match.group(1).lower()
        if kind in ("comment", "string", "preamble"):
            continue
        body, i, depth = "", match.end(), 1
        while i < len(text) and depth:  # read up to the entry's closing brace
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            body += text[i]
            i += 1
        fields = {"_type": kind}
        # name = {value with {nested} braces}  or  name = "value"  or  name = 2021
        for name, braced, quoted, bare in re.findall(
                r'(\w+)\s*=\s*(?:\{((?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*)\}|"([^"]*)"|(\w+))', body):
            fields[name.lower()] = clean(braced or quoted or bare)
        entries.append(fields)
    return entries


def clean(value: str) -> str:
    """Turn LaTeX bits into plain text: accents, dashes, braces, extra spaces."""
    # e.g. {\'e} -> é, \~n -> ñ, {\'\i} -> í (\i is a dotless i)
    value = re.sub(r"\\([" + re.escape("'`^\"~") + r"cv])\s*\{?\\?(\w)\}?",
                   lambda m: m.group(2) + ACCENTS[m.group(1)], value)
    value = value.replace("\\&", "&").replace("---", "—").replace("--", "–")
    value = re.sub(r"\$\\delta\$", "δ", value)
    value = value.replace("{", "").replace("}", "")
    return unicodedata.normalize("NFC", " ".join(value.split()))


# ---------- formatting ----------

def split_name(name: str) -> tuple[str, str]:
    """'Arnold, T. Elliott' or 'T. Elliott Arnold' -> ('Arnold', 'T. Elliott')."""
    if "," in name:
        last, first = name.split(",", 1)
    else:
        *first, last = name.split()
        first = " ".join(first)
    return last.strip(), first.strip()


def short_name(name: str) -> str:
    """'Arnold, T. Elliott' -> 'Arnold, T.E.'; also handles Scholar's 'Arnold, TE'."""
    last, first = split_name(name)
    initials = ""
    for part in re.split(r"[\s.]+", first):
        if re.fullmatch(r"[A-Z]{2,3}", part):  # 'TE' means two initials
            initials += "".join(c + "." for c in part)
        elif part:
            initials += part[0] + "."
    return f"{last}, {initials}" if initials else last


def member_keys() -> set[tuple[str, str]]:
    keys = set()
    for line in MEMBERS.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            last, first = split_name(line)
            keys.add((last.lower(), first[:1].lower()))
    return keys


def format_entry(e: dict, members: set) -> str:
    authors = []
    for a in e.get("author", "").split(" and "):
        if a.strip().lower() == "others":
            authors.append("et al.")
            continue
        last, first = split_name(a)
        text = html.escape(short_name(a))
        if (last.lower(), first[:1].lower()) in members:
            text = f"<strong>{text}</strong>"
        authors.append(text)

    line = (f'{", ".join(authors)} ({html.escape(e.get("year", "n.d."))}). '
            f'<span class="pub-title">{html.escape(e.get("title", "").rstrip("."))}.</span> ')

    kind = e["_type"]
    if kind in THESIS_LABEL:
        line += f'{THESIS_LABEL[kind]}, {html.escape(e.get("school", ""))}.'
    else:
        venue = e.get("journal") or e.get("booktitle") or ""
        details = ", ".join(x for x in (e.get("volume"), e.get("pages")) if x)
        if venue:
            prefix = "In: " if kind in ("incollection", "inbook") else ""
            line += f'{prefix}<span class="pub-venue">{html.escape(venue)}</span>'
            if kind in ("incollection", "inbook") and e.get("publisher"):
                line += f", {html.escape(e['publisher'])}"
            line += f", {html.escape(details)}." if details else "."

    links = []
    if e.get("doi"):
        doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", e["doi"])
        links.append(f'<a class="tag" href="https://doi.org/{html.escape(doi)}">DOI</a>')
    elif e.get("url"):
        links.append(f'<a class="tag" href="{html.escape(e["url"])}">Link</a>')
    if e.get("pdf"):
        links.append(f'<a class="tag" href="{html.escape(e["pdf"])}">PDF</a>')
    if links:
        line += f'\n      <div class="pub-links">{" ".join(links)}</div>'
    return f"    <li>\n      {line}\n    </li>"


def newest_first(entries: list[dict]) -> list[dict]:
    """Sort by year, newest first; within a year, later in the file comes first."""
    indexed = list(enumerate(entries))
    indexed.sort(key=lambda p: (p[1].get("year", "0"), p[0]), reverse=True)
    return [e for _, e in indexed]


def by_year(entries: list[dict], members: set) -> list[str]:
    """HTML for a list grouped under year headings."""
    blocks, year = [], None
    for e in entries:
        if e.get("year") != year:
            if year is not None:
                blocks.append("  </ul>")
            year = e.get("year")
            blocks.append(f'  <h3 class="pub-year">{html.escape(year or "Undated")}</h3>\n  <ul class="pubs">')
        blocks.append(format_entry(e, members))
    if entries:
        blocks.append("  </ul>")
    return blocks


# ---------- writing into the HTML ----------

def replace_between(path: Path, marker: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"(<!-- BEGIN {marker} -->).*?(\s*<!-- END {marker} -->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"Markers for '{marker}' not found in {path.name}")
    path.write_text(pattern.sub(lambda m: m.group(1) + "\n" + new + m.group(2), text),
                    encoding="utf-8")


def main() -> None:
    entries = newest_first(parse_bib(BIB.read_text(encoding="utf-8")))
    members = member_keys()

    grouped = {key: [e for e in entries if e["_type"] in types] for key, _, types in SECTIONS}
    known = set().union(*(types for _, _, types in SECTIONS))
    for e in entries:
        if e["_type"] not in known:
            print(f"  warning: @{e['_type']} isn't in any section, skipped: {e.get('title', '?')[:60]}")

    # Full page: a jump list, then each section grouped by year.
    present = [(key, title) for key, title, _ in SECTIONS if grouped[key]]
    jump = " · ".join(f'<a href="#{key}">{title}</a>' for key, title in present)
    blocks = [f'  <p class="jump">Jump to: {jump}</p>']
    for key, title in present:
        blocks.append(f'  <h2 id="{key}">{title}</h2>')
        blocks += by_year(grouped[key], members)
    replace_between(ROOT / "publications.html", "publications", "\n".join(blocks))

    # Homepage: most recent articles and chapters.
    recent = [format_entry(e, members) for e in grouped["articles"][:RECENT_COUNT]]
    replace_between(ROOT / "index.html", "recent-publications",
                    '  <ul class="pubs">\n' + "\n".join(recent) + "\n  </ul>")

    counts = ", ".join(f"{len(grouped[k])} {t.lower()}" for k, t, _ in SECTIONS)
    print(f"Wrote {len(entries)} entries to publications.html ({counts}) "
          f"and the {len(recent)} most recent articles to index.html")
    for e in entries:
        missing = [f for f in ("author", "title", "year") if not e.get(f)]
        if missing:
            print(f"  warning: an entry is missing {', '.join(missing)}: {e.get('title', '?')[:60]}")


if __name__ == "__main__":
    main()

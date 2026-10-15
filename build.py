#!/usr/bin/env python3
"""Build the Bendor Lab website into _site/.

    python build.py            # build
    python build.py --serve    # build, then preview at http://localhost:8000

Content lives in data/*.yml, page layouts in templates/, styles and images in static/.
"""
import datetime as dt
import html
import json
import re
import unicodedata
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
DATA = ROOT / "data"

NAV = [
    ("research", "Research"),
    ("people", "People"),
    ("publications", "Publications"),
    ("photos", "Photos"),
    ("code", "Code and data"),
    ("positions", "Join the lab"),
    ("contact", "Contact"),
]
PAGE_TITLES = {"research": "Research", "people": "People", "publications": "Publications",
               "photos": "Photos", "code": "Code and data", "positions": "Join the lab", "contact": "Contact",
               "news": "News"}
HOME_NEWS = 4  # news items shown on the home page

# Descriptions shown by search engines and in link previews (keep each under about 155 characters).
DESCRIPTIONS = {
    "": "The Bendor Lab at UCL studies how neocortex and hippocampus encode information and "
        "communicate, to understand memory, perception, predictive coding and sleep.",
    "research": "Research in the Bendor Lab at UCL: hippocampal replay, memory triage, predictive coding, "
                "and how auditory cortex codes time and pitch.",
    "people": "Current members and alumni of the Bendor Lab, Institute of Behavioural Neuroscience, UCL.",
    "publications": "Publications from the Bendor Lab at UCL, updated each week from ORCID, Crossref and PubMed.",
    "photos": "Photos of the Bendor Lab at UCL.",
    "code": "Code and data from the Bendor Lab's hippocampal replay papers.",
    "positions": "How to join the Bendor Lab at UCL, and the UCL programmes students usually join through.",
    "contact": "Contact details for the Bendor Lab, UCL Department of Experimental Psychology, "
               "26 Bedford Way, London WC1H 0AP.",
    "news": "News from the Bendor Lab at UCL.",
}


def load(name):
    return yaml.safe_load((DATA / f"{name}.yml").read_text(encoding="utf-8")) or {}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def initials(name):
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else ""


def prepare_news(news):
    """News items, newest first, with the date shown as month and year."""
    items = []
    for n in news.get("items") or []:
        if not n or not str(n.get("text") or "").strip():
            continue
        d = n.get("date")
        if isinstance(d, dt.datetime):
            d = d.date()
        if not isinstance(d, dt.date):
            try:
                d = dt.date.fromisoformat(str(d)[:10])
            except ValueError:
                print(f"warning: news item '{n['text'][:40]}' has no valid date (use YYYY-MM-DD)", file=sys.stderr)
                d = dt.date.min
        items.append({**n, "sort": d, "when": d.strftime("%B %Y") if d != dt.date.min else ""})
    items.sort(key=lambda n: n["sort"], reverse=True)
    return items


_SIZES = {}


def image_size(path):
    """(width, height) of a local image such as /static/images/x.webp, or None."""
    path = str(path or "")
    if not path or re.match(r"^https?://", path):
        return None
    if path not in _SIZES:
        from PIL import Image
        try:
            with Image.open(ROOT / path.lstrip("/")) as im:
                _SIZES[path] = im.size
        except OSError:
            _SIZES[path] = None
    return _SIZES[path]


def dims(path):
    """width and height attributes for an <img>, so the page does not jump as images load."""
    size = image_size(path)
    return Markup(f' width="{size[0]}" height="{size[1]}"') if size else ""


def tidy_link(url):
    """Canonical https form of free full-text links (old PubMed Central and cell.com addresses)."""
    url = (url or "").strip()
    m = re.match(r"^https?://(?:www\.)?ncbi\.nlm\.nih\.gov/pmc/articles/(?:PMC)?(\d+)/?$", url, re.I)
    if m:
        return f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{m.group(1)}/"
    return re.sub(r"^http://(www\.)?cell\.com", "https://www.cell.com", url)


def long_date(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


# --------------------------------------------------------------------------- publications

def _norm(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]+", " ", text.lower().replace("-", " ")).split()


def lab_people(people):
    """(first name, surname tokens) for everyone listed on the People page."""
    out = []
    for person in (people.get("members") or []) + (people.get("alumni") or []):
        tokens = _norm(person.get("name"))
        if len(tokens) >= 2:
            out.append((tokens[0], tokens[1:]))
    return out


def is_lab_member(family, given, lab):
    """Match an author to a lab member by surname and the start of the first name.

    The first two letters must agree when both names are spelled out, which copes with
    short forms (Masa, Masahiro; Prez, Przemyslaw) but keeps apart, for example, John and
    Julie with the same surname. Surnames match when the lab name is the start of the
    published one (Huelin; Huelin Gorriz).
    """
    fam = _norm(family)
    giv = _norm(given)
    if not fam:
        return False
    for first, surname in lab:
        if fam[:len(surname)] != surname:
            continue
        g = giv[0] if giv else ""
        if len(g) >= 2 and len(first) >= 2:
            if g[:2] == first[:2]:
                return True
        elif g[:1] == first[:1]:
            return True
    return False


def prepare_publications(settings, lab):
    raw = json.loads((DATA / "publications.json").read_text(encoding="utf-8"))
    highlight = set(settings.get("highlight") or [])
    # sections set in publications.yml apply straight away, before the next weekly refresh
    section_of = {str(i.get("doi") or "").lower(): i["section"]
                  for i in (settings.get("include") or []) if i and i.get("doi") and i.get("section")}
    items = []
    for p in raw["items"]:
        p = dict(p)
        p["section"] = section_of.get(str(p.get("doi") or "").lower(), p.get("section"))
        authors = p.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        details = p.get("author_details") or []
        if len(details) != len(authors):
            # no full names available: split "Huelin Gorriz M" into surname and initials
            details = [{"family": " ".join(a.split()[:-1]) or a, "given": a.split()[-1] if len(a.split()) > 1 else ""}
                       for a in authors]
        parts = []
        for name, det in zip(authors, details):
            bold = name in highlight or is_lab_member(det.get("family"), det.get("given"), lab)
            parts.append(f"<strong>{html.escape(name)}</strong>" if bold else html.escape(name))
        p["authors_html"] = Markup(", ".join(parts))
        p["url"] = f"https://doi.org/{p['doi']}" if p.get("doi") else p.get("url", "")
        oa = tidy_link(p.get("oa_url"))
        same_as_doi = bool(p.get("doi")) and oa.lower().rstrip("/").endswith(p["doi"].lower())
        p["oa_link"] = "" if (not oa or same_as_doi) else oa
        p["oa_label"] = "Free PDF" if p.get("oa_pdf") else "Free full text"
        p["open_access"] = bool(oa)
        items.append(p)
    items.sort(key=lambda p: (p.get("date") or "", p["title"]), reverse=True)

    order = list(settings.get("sections") or [])
    for p in items:
        if p["section"] not in order:
            order.append(p["section"])
    sections = []
    for name in order:
        group = [dict(p) for p in items if p["section"] == name]
        last_year = None
        for p in group:
            p["first_of_year"] = p["year"] != last_year
            last_year = p["year"]
        if group:
            sections.append((name, group))
    by_doi = {p["doi"].lower(): p for p in items if p.get("doi")}
    checked = DATA / ".last_checked"
    last = checked.read_text().strip() if checked.exists() else raw["updated"]
    return items, sections, by_doi, long_date(last)


# --------------------------------------------------------------------------- build

def build():
    site = load("site")
    people = load("people")
    photos = load("photos")
    positions = load("positions")
    research = load("research")
    pub_settings = load("publications")
    code = load("code")
    news = prepare_news(load("news")) if (DATA / "news.yml").exists() else []
    items, sections, by_doi, updated = prepare_publications(pub_settings, lab_people(people))

    for m in people.get("members", []):
        m["initials"] = initials(m.get("name") or "")
    groups = list(people.get("alumni_groups") or [])
    people["members"] = people.get("members") or []
    people["alumni"] = people.get("alumni") or []
    for a in people["alumni"]:
        if a.get("group") not in groups:
            groups.append(a.get("group"))
    alumni = [(g, [a for a in people["alumni"] if a.get("group") == g]) for g in groups]
    alumni = [(g, rows) for g, rows in alumni if rows]

    themes = []
    photos["photos"] = [p for p in (photos.get("photos") or []) if p and p.get("image")]
    positions["openings"] = positions.get("openings") or []
    for t in research.get("themes") or []:
        pubs = [by_doi[d.lower()] for d in (t.get("papers") or []) if d and d.lower() in by_doi]
        missing = [d for d in (t.get("papers") or []) if d and d.lower() not in by_doi]
        for d in missing:
            print(f"warning: research theme '{t['title']}' lists {d}, which is not in the publication list", file=sys.stderr)
        themes.append({**t, "pubs": pubs})

    recent = [p for p in items if p["section"] != "Book chapters"][:4]

    # Code and data: entries from data/code.yml, each tied to a paper by DOI, plus any other
    # public repositories in the lab's GitHub organisation (data/repos.json, written by the
    # weekly workflow).
    code_entries = []
    listed = set()
    for e in code.get("entries") or []:
        paper = by_doi.get(str(e.get("doi") or "").lower())
        links = [l for l in (e.get("links") or []) if l and l.get("url")]
        listed.update(l["url"].rstrip("/").lower() for l in links)
        code_entries.append({**e, "paper": paper, "links": links})
    code_entries.sort(key=lambda e: (e["paper"] or {}).get("date", ""), reverse=True)
    extra_repos = []
    repos_file = DATA / "repos.json"
    if repos_file.exists() and code.get("list_other_repositories"):
        skip = {str(x).lower() for x in (code.get("hide_repositories") or [])}
        for r in json.loads(repos_file.read_text(encoding="utf-8")):
            url = (r.get("html_url") or "").rstrip("/")
            if (not url or r.get("fork") or r.get("archived") or r.get("private") or r.get("size") == 0
                    or url.lower() in listed or r.get("name", "").lower() in skip):
                continue
            extra_repos.append(r)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["slugify"] = slugify
    env.globals.update(dims=dims, image_size=image_size)
    common = dict(site=site, people=people, photos=photos, positions=positions, research=research,
                  nav=NAV, build_id=dt.datetime.now().strftime("%Y%m%d%H%M"))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT / "static")

    pages = [("index.html", "", {"recent": recent})] + [
        (f"{slug}.html", slug, {}) for slug, _ in NAV
    ] + ([("news.html", "news", {})] if news else []) + [("404.html", "404", {})]

    for template, slug, extra in pages:
        if slug == "404":
            root, dest = "/", OUT / "404.html"
        elif slug:
            root, dest = "../", OUT / slug / "index.html"
        else:
            root, dest = "", OUT / "index.html"

        def asset(path, _root=root):
            return path if re.match(r"^https?://", path or "") else _root + str(path or "").lstrip("/")

        ctx = dict(common, root=root, slug=slug if slug != "404" else "", asset=asset,
                   description=DESCRIPTIONS.get(slug, ""),
                   page_title=PAGE_TITLES.get(slug, "Page not found" if slug == "404" else ""),
                   pub_sections=sections, pubs_updated=updated, themes=themes, alumni=alumni,
                   code=code, code_entries=code_entries, extra_repos=extra_repos,
                   news=news, home_news=HOME_NEWS, **extra)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    # search-engine helpers
    urls = [f"{site['url']}/"] + [f"{site['url']}/{slug}/" for slug, _ in NAV] + ([f"{site['url']}/news/"] if news else [])
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc></url>\n" for u in urls) + "</urlset>\n", encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {site['url']}/sitemap.xml\n", encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(pages)} pages and {len(items)} publications into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    build()
    if "--serve" in sys.argv:
        import functools
        import http.server
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(OUT))
        print("Preview at http://localhost:8000  (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer(("", 8000), handler).serve_forever()

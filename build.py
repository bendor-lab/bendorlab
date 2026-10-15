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
               "photos": "Photos", "code": "Code and data", "positions": "Join the lab", "contact": "Contact"}


def load(name):
    return yaml.safe_load((DATA / f"{name}.yml").read_text(encoding="utf-8")) or {}


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def initials(name):
    parts = [p for p in re.split(r"\s+", name.strip()) if p]
    return (parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")).upper() if parts else ""


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
    items = []
    for p in raw["items"]:
        p = dict(p)
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
        oa = (p.get("oa_url") or "").strip()
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
    if repos_file.exists():
        skip = {str(x).lower() for x in (code.get("hide_repositories") or [])}
        for r in json.loads(repos_file.read_text(encoding="utf-8")):
            url = (r.get("html_url") or "").rstrip("/")
            if (not url or r.get("fork") or r.get("archived") or r.get("private")
                    or url.lower() in listed or r.get("name", "").lower() in skip):
                continue
            extra_repos.append(r)

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["slugify"] = slugify
    common = dict(site=site, people=people, photos=photos, positions=positions, research=research,
                  nav=NAV, build_id=dt.datetime.now().strftime("%Y%m%d%H%M"))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT / "static")

    pages = [("index.html", "", {"recent": recent})] + [
        (f"{slug}.html", slug, {}) for slug, _ in NAV
    ] + [("404.html", "404", {})]

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
                   page_title=PAGE_TITLES.get(slug, "Page not found" if slug == "404" else ""),
                   pub_sections=sections, pubs_updated=updated, themes=themes, alumni=alumni,
                   code=code, code_entries=code_entries, extra_repos=extra_repos, **extra)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(env.get_template(template).render(**ctx), encoding="utf-8")

    # search-engine helpers
    urls = [f"{site['url']}/"] + [f"{site['url']}/{slug}/" for slug, _ in NAV]
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

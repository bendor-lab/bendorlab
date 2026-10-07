#!/usr/bin/env python3
"""Build the Bendor Lab website into _site/.

    python build.py            # build
    python build.py --serve    # build, then preview at http://localhost:8000

Content lives in data/*.yml, page layouts in templates/, styles and images in static/.
"""
import datetime as dt
import html
import json
import math
import random
import re
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
    ("positions", "Join the lab"),
    ("contact", "Contact"),
]
PAGE_TITLES = {"research": "Research", "people": "People", "publications": "Publications",
               "photos": "Photos", "positions": "Join the lab", "contact": "Contact"}


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

def prepare_publications(settings):
    raw = json.loads((DATA / "publications.json").read_text(encoding="utf-8"))
    highlight = set(settings.get("highlight") or [])
    items = []
    for p in raw["items"]:
        p = dict(p)
        authors = p.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in authors.split(",") if a.strip()]
        parts = [f"<strong>{html.escape(a)}</strong>" if a in highlight else html.escape(a) for a in authors]
        p["authors_html"] = Markup(", ".join(parts))
        p["url"] = f"https://doi.org/{p['doi']}" if p.get("doi") else p.get("url", "")
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


# --------------------------------------------------------------------------- replay figure

def replay_svg():
    """Raster of place-cell spikes with one time-compressed replay sequence under a ripple.

    Generated with a fixed seed so the figure is identical on every build.
    """
    rng = random.Random(7)
    W, H = 1000, 170
    n_cells = 16
    top, row_h = 52, 7.2
    ev_start, ev_step = 412, 11.5          # replay sequence: one cell after another
    ev_end = ev_start + ev_step * n_cells
    centre = (ev_start + ev_end) / 2

    # LFP trace with a ripple oscillation centred on the replay event
    pts = []
    for x in range(0, W + 1, 2):
        base = 4 * math.sin(x / 37.0) + 2.2 * math.sin(x / 11.3 + 1.2) + rng.uniform(-1.4, 1.4)
        env = math.exp(-((x - centre) / 62.0) ** 2)
        ripple = 15 * env * math.sin(x / 2.15)
        sharp = -11 * env
        pts.append(f"{x},{24 + base + ripple + sharp:.1f}")
    trace = f'<polyline class="lfp" points="{" ".join(pts)}"/>'

    background, sequence = [], []
    for i in range(n_cells):
        y = top + i * row_h
        # sparse background firing, kept clear of the replay window
        x = rng.uniform(0, 40)
        while x < W:
            if not (ev_start - 30 < x < ev_end + 30):
                background.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{y:.1f}" y2="{y + row_h - 2:.1f}"/>')
            x += rng.expovariate(1 / 120.0)
        # each cell's burst during the replay event, in sequence
        t0 = ev_start + i * ev_step + rng.uniform(-2, 2)
        for k in range(rng.choice((1, 2, 2, 3))):
            sx = t0 + k * 3.2
            sequence.append(
                f'<line style="--i:{i}" x1="{sx:.1f}" x2="{sx:.1f}" y1="{y:.1f}" y2="{y + row_h - 2:.1f}"/>'
            )
    svg = (
        f'<svg class="replay-svg" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" '
        f'role="img" aria-label="Spike raster of {n_cells} cells firing in sequence during a ripple">'
        f'{trace}<g class="bg-spikes">{"".join(background)}</g>'
        f'<g class="seq-spikes">{"".join(sequence)}</g></svg>'
    )
    return Markup(svg)


# --------------------------------------------------------------------------- build

def build():
    site = load("site")
    people = load("people")
    photos = load("photos")
    positions = load("positions")
    research = load("research")
    pub_settings = load("publications")
    items, sections, by_doi, updated = prepare_publications(pub_settings)

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

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=select_autoescape(["html"]))
    env.filters["slugify"] = slugify
    common = dict(site=site, people=people, photos=photos, positions=positions, research=research,
                  nav=NAV, build_id=dt.datetime.now().strftime("%Y%m%d%H%M"))

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    shutil.copytree(ROOT / "static", OUT / "static")

    pages = [("index.html", "", {"recent": recent, "replay_svg": replay_svg()})] + [
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
                   pub_sections=sections, pubs_updated=updated, themes=themes, alumni=alumni, **extra)
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

#!/usr/bin/env python3
"""Refresh data/publications.json from ORCID, Crossref and PubMed.

Run by the GitHub Action every week (and on every push). It can also be run
by hand:  python scripts/fetch_publications.py

Safety: if the databases fail or return a much shorter list than last time,
the existing publications.json is left untouched and the site keeps showing
the last good list.
"""
import datetime as dt
import difflib
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "data" / "publications.yml"
OUTPUT = ROOT / "data" / "publications.json"
LAST_CHECKED = ROOT / "data" / ".last_checked"  # not saved in the repository
CHANGES = ROOT / "data" / ".changes.md"         # read by the workflow to open a GitHub issue
PROBLEMS = ROOT / "data" / ".problems.md"       # likewise, when the refresh did not work
UA = "bendorlab-website/1.0 (https://www.bendorlab.com; mailto:d.bendor@ucl.ac.uk)"

PREPRINT_SECTION = "Preprints"
ARTICLE_SECTION = "Peer-reviewed articles"
COMMENT_SECTION = "Commentary"
CHAPTER_SECTION = "Book chapters"

SKIP_TYPES = {"peer-review", "component", "dataset", "journal-issue", "report-component", "grant", "other"}
SKIP_TITLE = re.compile(r"^\s*(erratum|errata|correction|corrigendum|author response|decision letter|retraction)\b", re.I)


def log(msg):
    print(msg, file=sys.stderr)


def get_json(url, headers=None, tries=3):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            if attempt == tries - 1:
                raise
            log(f"  retrying {url} ({e})")
            time.sleep(5 * (attempt + 1))


def norm_doi(doi):
    if not doi:
        return None
    d = str(doi).strip().lower()
    d = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", d)
    d = re.sub(r"^doi:\s*", "", d)
    # eLife publishes versioned DOIs (…/elife.86464.2) and review documents (…/elife.86464.sa2)
    if re.match(r"^10\.7554/elife\.\d+\.sa\d+$", d):
        return None
    d = re.sub(r"^(10\.7554/elife\.\d+)\.\d{1,2}$", r"\1", d)
    return d


def norm_title(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    t = html.unescape(t).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def clean_title(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    t = html.unescape(re.sub(r"\s+", " ", t)).strip()
    return t.rstrip(".")


def initials(given):
    parts = [p for p in re.split(r"[\s.\-]+", given or "") if p]
    return "".join(p[0].upper() for p in parts)


def format_author(a):
    if a.get("family"):
        ini = initials(a.get("given", ""))
        return f"{a['family']} {ini}".strip()
    return a.get("name", "").strip()


def tidy_pages(pages):
    parts = [x.strip() for x in str(pages).split("-")]
    if len(parts) == 2 and parts[0] == parts[1]:
        return parts[0]
    return "\u2013".join(parts)


# --------------------------------------------------------------------------- sources

def from_orcid(orcid):
    found = {}
    data = get_json(f"https://pub.orcid.org/v3.0/{orcid}/works")
    for group in data.get("group", []):
        s = group["work-summary"][0]
        ids = (s.get("external-ids") or {}).get("external-id", []) or []
        dois = [norm_doi(e["external-id-value"]) for e in ids if e["external-id-type"] == "doi"]
        dois = [d for d in dois if d]
        if dois:
            found[dois[0]] = {"orcid_type": s.get("type")}
    log(f"ORCID: {len(found)} works with DOIs")
    return found


def from_crossref_orcid(orcid):
    found = {}
    url = f"https://api.crossref.org/works?filter=orcid:{orcid}&rows=500&select=DOI,type"
    for it in get_json(url)["message"]["items"]:
        if it.get("type") in SKIP_TYPES:
            continue
        d = norm_doi(it["DOI"])
        if d:
            found[d] = {"crossref_type": it.get("type")}
    log(f"Crossref (ORCID-linked): {len(found)} works")
    return found


def from_pubmed(query):
    found = {}
    q = urllib.parse.quote(query)
    ids = get_json(f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&retmode=json&retmax=500&term={q}")["esearchresult"]["idlist"]
    if not ids:
        return found
    res = get_json("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=pubmed&retmode=json&id=" + ",".join(ids))["result"]
    for uid in res.get("uids", []):
        rec = res[uid]
        doi = next((a["value"] for a in rec.get("articleids", []) if a["idtype"] == "doi"), None)
        d = norm_doi(doi)
        if d:
            found[d] = {"pmid": uid, "pubtypes": rec.get("pubtype", [])}
    log(f"PubMed: {len(found)} works")
    return found


def crossref_record(doi):
    msg = get_json("https://api.crossref.org/works/" + urllib.parse.quote(doi))["message"]
    date_parts = None
    for key in ("published-print", "published-online", "issued", "posted", "created"):
        dp = (msg.get(key) or {}).get("date-parts")
        if dp and dp[0] and dp[0][0]:
            date_parts = dp[0]
            break
    date_parts = (date_parts or [0]) + [1, 1]
    ctype = msg.get("type", "")
    venue = (msg.get("container-title") or [""])[0]
    if ctype == "posted-content":
        inst = msg.get("institution") or []
        venue = (inst[0].get("name") if inst else "") or msg.get("group-title") or msg.get("publisher", "")
    relation = msg.get("relation") or {}
    published_as = [norm_doi(r.get("id")) for r in relation.get("is-preprint-of", []) if r.get("id-type") == "doi"]
    return {
        "doi": doi,
        "type": ctype,
        "title": clean_title((msg.get("title") or [""])[0]),
        "authors": [format_author(a) for a in msg.get("author", []) if format_author(a)],
        "venue": html.unescape(venue),
        "volume": msg.get("volume", ""),
        "issue": msg.get("issue", ""),
        "pages": tidy_pages(msg.get("page") or msg.get("article-number") or ""),
        "year": int(date_parts[0]),
        "date": f"{date_parts[0]:04d}-{date_parts[1]:02d}-{date_parts[2]:02d}",
        "published_as": [d for d in published_as if d],
    }


# --------------------------------------------------------------------------- reports

def short_citation(p):
    authors = p.get("authors") or []
    who = authors[0] + (" et al." if len(authors) > 2 else (", " + authors[1] if len(authors) == 2 else "")) if authors else ""
    link = f"https://doi.org/{p['doi']}" if p.get("doi") else ""
    return f"- {who} ({p.get('year', '')}). {p.get('title', '')}. *{p.get('venue', '')}*. {link}".strip()


def write_changes(added, removed):
    lines = []
    if added:
        lines += ["These papers were found automatically and added to the website:", ""]
        lines += [short_citation(p) for p in added] + [""]
    if removed:
        lines += ["These papers are no longer listed (usually because a preprint's journal version appeared):", ""]
        lines += [short_citation(p) for p in removed] + [""]
    lines += [
        "If anything here is wrong, hide it in Pages CMS under **Publications > Papers to hide**,",
        "or put a missing paper back under **Papers to always list**. Close this issue once you have looked.",
    ]
    CHANGES.write_text("\n".join(lines) + "\n")


def write_problems(problems):
    PROBLEMS.write_text(
        "The weekly publication refresh ran into problems, so the website is still showing the last good list.\n\n"
        + "\n".join(f"- {x}" for x in problems)
        + "\n\nThis is usually a temporary outage at ORCID, Crossref or PubMed and fixes itself the following week. "
        "If it keeps happening, check the latest run in the Actions tab.\n"
    )


# --------------------------------------------------------------------------- main

def main():
    settings = yaml.safe_load(SETTINGS.read_text()) or {}
    previous = {}
    if OUTPUT.exists():
        previous = {p["doi"]: p for p in json.loads(OUTPUT.read_text()).get("items", []) if p.get("doi")}

    include = {}
    manual = []
    for entry in settings.get("include") or []:
        d = norm_doi(entry.get("doi"))
        if d:
            include[d] = entry
        else:
            manual.append(entry)
    highlight = set(settings.get("highlight") or [])
    exclude = {norm_doi(e.get("doi") if isinstance(e, dict) else e) for e in settings.get("exclude") or []}

    discovered = {}
    sources_ok = 0
    problems = []
    for f in (CHANGES, PROBLEMS):
        f.unlink(missing_ok=True)
    for name, fn, arg in (
        ("orcid", from_orcid, settings.get("orcid")),
        ("crossref", from_crossref_orcid, settings.get("orcid")),
        ("pubmed", from_pubmed, settings.get("pubmed_query")),
    ):
        if not arg:
            continue
        try:
            for d, info in fn(arg).items():
                discovered.setdefault(d, {}).update(info)
            sources_ok += 1
        except Exception as e:  # noqa: BLE001
            log(f"WARNING: {name} lookup failed: {e}")
            problems.append(f"Could not reach {name.upper() if name == 'orcid' else name.title()}: {e}")

    dois = [d for d in dict.fromkeys(list(include) + list(discovered)) if d and d not in exclude]

    items = []
    for d in dois:
        try:
            rec = crossref_record(d)
        except Exception as e:  # noqa: BLE001
            if d in previous:
                log(f"  Crossref failed for {d}; keeping previous details ({e})")
                rec = dict(previous[d])
            else:
                log(f"  Crossref failed for {d}; skipping ({e})")
                problems.append(f"Could not get details for https://doi.org/{d} from Crossref: {e}")
                continue
        time.sleep(0.15)
        info = discovered.get(d, {})
        if d not in include:
            if rec["type"] in SKIP_TYPES or SKIP_TITLE.search(rec["title"]):
                continue
            # anything found automatically must list a highlighted name (e.g. "Bendor D") as an author
            if highlight and not any(a in highlight for a in rec["authors"]):
                log(f"  skipping {d}: no listed author matches {sorted(highlight)}")
                continue
        # section
        if rec["type"] == "posted-content" or info.get("orcid_type") == "preprint":
            section = PREPRINT_SECTION
        elif rec["type"] in ("book-chapter", "book", "book-part", "book-section"):
            section = CHAPTER_SECTION
        elif "Comment" in info.get("pubtypes", []) or "Editorial" in info.get("pubtypes", []):
            section = COMMENT_SECTION
        else:
            section = ARTICLE_SECTION
        rec["section"] = section
        if d in include:  # manual overrides win
            for k, v in include[d].items():
                if k != "doi" and v not in (None, ""):
                    rec[k] = clean_title(v) if k == "title" else v
            if isinstance(rec.get("authors"), str):
                rec["authors"] = [a.strip() for a in rec["authors"].split(",") if a.strip()]
        rec["pmid"] = info.get("pmid", rec.get("pmid", ""))
        items.append(rec)

    for entry in manual:
        rec = {k: v for k, v in entry.items()}
        if isinstance(rec.get("authors"), str):
            rec["authors"] = [a.strip() for a in rec["authors"].split(",") if a.strip()]
        rec.setdefault("doi", "")
        rec.setdefault("section", ARTICLE_SECTION)
        rec["year"] = int(rec.get("year") or 0)
        rec.setdefault("date", f"{rec['year']:04d}-01-01")
        rec["title"] = clean_title(rec.get("title", ""))
        items.append(rec)

    # Drop a preprint once its journal version is listed, and duplicate preprints of the same paper
    published = [p for p in items if p["section"] != PREPRINT_SECTION]
    published_dois = {p.get("doi") for p in published}
    published_titles = [norm_title(p["title"]) for p in published]
    kept, seen_preprints = [], []
    # prefer bioRxiv/openRxiv over Research Square when the same preprint is on both
    items.sort(key=lambda p: (p["section"] == PREPRINT_SECTION and str(p.get("doi", "")).startswith("10.21203")))
    for p in items:
        if p["section"] == PREPRINT_SECTION and p.get("doi") not in include:
            t = norm_title(p["title"])
            if any(x in published_dois for x in p.get("published_as", [])):
                continue
            if any(difflib.SequenceMatcher(None, t, pt).ratio() >= 0.85 for pt in published_titles):
                continue
            if any(difflib.SequenceMatcher(None, t, st).ratio() >= 0.9 for st in seen_preprints):
                continue
            seen_preprints.append(t)
        kept.append(p)

    # If any database failed, keep everything that was listed before (unless now hidden),
    # so a temporary outage can add papers but never remove them.
    if sources_ok < len([a for a in (settings.get("orcid"), settings.get("orcid"), settings.get("pubmed_query")) if a]):
        kept_dois = {p.get("doi") for p in kept}
        for d, prev in previous.items():
            if d not in kept_dois and d not in exclude:
                kept.append(prev)

    kept.sort(key=lambda p: (p.get("date", ""), p["title"]), reverse=True)

    if sources_ok == 0:
        log("No database could be reached; leaving publications.json unchanged.")
        write_problems(problems or ["No database could be reached."])
        return 2
    if previous and len(kept) < 0.8 * len(previous):
        msg = f"The new list had {len(kept)} papers versus {len(previous)} before, so it was not used."
        log(msg)
        write_problems(problems + [msg])
        return 2

    today = dt.date.today().isoformat()
    LAST_CHECKED.write_text(today + "\n")
    old_items = json.loads(OUTPUT.read_text()).get("items") if OUTPUT.exists() else None
    if old_items == json.loads(json.dumps(kept, ensure_ascii=False)):
        log(f"No change: {len(kept)} publications")
        if problems:
            write_problems(problems)
            return 2
        return 0
    OUTPUT.write_text(json.dumps({"updated": today, "items": kept}, indent=1, ensure_ascii=False) + "\n")
    log(f"Wrote {len(kept)} publications to {OUTPUT.relative_to(ROOT)}")

    # Report what changed, leaving out edits made deliberately in publications.yml
    kept_dois = {p.get("doi") for p in kept if p.get("doi")}
    added = [p for p in kept if p.get("doi") and p["doi"] not in previous and p["doi"] not in include]
    removed = [p for d, p in previous.items() if d not in kept_dois and d not in exclude]
    if previous and (added or removed):
        write_changes(added, removed)
    if problems:
        write_problems(problems)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

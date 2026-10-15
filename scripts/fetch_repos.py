#!/usr/bin/env python3
"""List the public repositories of the lab's GitHub organisation into data/repos.json.

Run by the GitHub workflow before each build. The Code and data page shows any
repository not already linked from data/code.yml. If GitHub cannot be reached, the
page is built without the extra list. Empty repositories are not shown.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "repos.json"


def main():
    org = (yaml.safe_load((ROOT / "data" / "code.yml").read_text()) or {}).get("github_org")
    if not org:
        return 0
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "bendorlab-website"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repos, page = [], 1
    try:
        while True:
            url = f"https://api.github.com/orgs/{org}/repos?type=public&per_page=100&page={page}"
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
                batch = json.load(r)
            if not batch:
                break
            repos += [{k: x.get(k) for k in ("name", "html_url", "description", "fork", "archived", "private", "pushed_at", "size")}
                      for x in batch]
            page += 1
    except Exception as e:  # noqa: BLE001
        print(f"Could not list repositories for {org}: {e}", file=sys.stderr)
        return 0
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    OUT.write_text(json.dumps(repos, indent=1) + "\n")
    print(f"Listed {len(repos)} public repositories in {org}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Copyright (c) 2025-2026 Alan He. Licensed under AGPL-3.0. See LICENSE.
"""Push sitemap URLs to IndexNow (Bing, Yandex, Naver, Seznam).

Why this exists: GA for Jun-Aug 2026 shows 22 google/organic sessions against
18 from Bing across ~10k sitemap URLs — Google is not crawling the long tail
and Bing converts better anyway (2m12s vs 21s average engagement). IndexNow
is push, not wait-to-be-crawled, so it is the cheapest lever on that gap.

Submits in batches with a pause between them: dumping ten thousand URLs at
once on a low-traffic domain reads as spam, and the protocol caps a request at
10,000 URLs regardless.

Usage:
    python -m backend.tools.indexnow_submit --dry-run           # show plan
    python -m backend.tools.indexnow_submit --limit 500         # first slice
    python -m backend.tools.indexnow_submit --all               # everything

The key file must be reachable at https://valuescope.app/<key>.txt — it lives
in frontend/public/ and ships with the Vercel build. Verify it is live before
a real submit; IndexNow rejects the whole batch if the key does not resolve.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

HOST = "valuescope.app"
SITEMAP_URL = f"https://{HOST}/sitemap.xml"
ENDPOINT = "https://api.indexnow.org/indexnow"
BATCH_SIZE = 1000          # well under the 10k protocol cap
PAUSE_SECONDS = 2.0
_PUBLIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "frontend", "public",
)


def discover_key() -> str:
    """The IndexNow key is the basename of the 32-hex .txt file in public/."""
    env = os.environ.get("INDEXNOW_KEY", "").strip()
    if env:
        return env
    matches = [
        os.path.basename(p)[:-4]
        for p in glob.glob(os.path.join(_PUBLIC_DIR, "*.txt"))
        if re.fullmatch(r"[0-9a-f]{32}", os.path.basename(p)[:-4])
    ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        sys.exit(f"No IndexNow key file found in {_PUBLIC_DIR} (expected <32-hex>.txt)")
    sys.exit(f"Multiple key files in {_PUBLIC_DIR}: {matches} — set INDEXNOW_KEY")


def fetch_sitemap_urls() -> list[str]:
    with urllib.request.urlopen(SITEMAP_URL, timeout=60) as r:
        root = ET.fromstring(r.read())
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", ns) if loc.text]


def verify_key_live(key: str) -> bool:
    """IndexNow rejects a batch whose key file does not resolve — check first."""
    try:
        with urllib.request.urlopen(f"https://{HOST}/{key}.txt", timeout=15) as r:
            return r.read().decode().strip() == key
    except Exception as e:
        print(f"  key check failed: {e}")
        return False


def submit(key: str, urls: list[str]) -> int:
    import json
    payload = json.dumps({
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
        "urlList": urls,
    }).encode()
    req = urllib.request.Request(
        ENDPOINT, data=payload, headers={"Content-Type": "application/json; charset=utf-8"}
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=500,
                    help="max URLs to submit (default 500; use --all for every URL)")
    ap.add_argument("--all", action="store_true", help="submit the entire sitemap")
    ap.add_argument("--dry-run", action="store_true", help="show what would be sent")
    args = ap.parse_args()

    key = discover_key()
    urls = fetch_sitemap_urls()
    if not args.all:
        urls = urls[: args.limit]

    print(f"key      : {key}")
    print(f"sitemap  : {SITEMAP_URL}")
    print(f"urls     : {len(urls)}")
    print(f"batches  : {(len(urls) + BATCH_SIZE - 1) // BATCH_SIZE} x {BATCH_SIZE}")
    if urls[:3]:
        print("sample   : " + ", ".join(urls[:3]))

    if args.dry_run:
        print("\n--dry-run: nothing submitted.")
        return

    print("\nverifying key is live...")
    if not verify_key_live(key):
        sys.exit(f"Key file https://{HOST}/{key}.txt is not live or does not match.\n"
                 "Deploy the frontend first, then rerun.")
    print("  ok")

    for i in range(0, len(urls), BATCH_SIZE):
        batch = urls[i : i + BATCH_SIZE]
        status = submit(key, batch)
        print(f"  batch {i // BATCH_SIZE + 1}: {len(batch)} urls -> HTTP {status}")
        if i + BATCH_SIZE < len(urls):
            time.sleep(PAUSE_SECONDS)
    print("done. IndexNow accepts asynchronously — 200/202 means queued, not indexed.")


if __name__ == "__main__":
    main()

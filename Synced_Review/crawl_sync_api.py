"""Crawl SyncedReview homepage (https://syncedreview.com/) and fetch article title/date/content."""

from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import List, Optional

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
from urllib.parse import urljoin


# ----------------- Config -----------------
BASE = "https://syncedreview.com"
LIST_URL = f"{BASE}/"
HEADERS = {"User-Agent": "synced-crawler/0.1"}
# ------------------------------------------


def fetch_html(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_list(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for h2 in soup.select("h2.entry-title a[href]"):
        href = h2["href"]
        if href.startswith("/"):
            href = urljoin(BASE, href)
        links.append(href)
    return links


def fetch_detail(url: str) -> tuple[str, str, str]:
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    date = ""
    time_tag = soup.find("time")
    if time_tag and time_tag.has_attr("datetime"):
        date = time_tag["datetime"][:10]

    content_node = soup.select_one("div.entry-content") or soup.select_one("div.article-content")

    def absolutize(u: str) -> str:
        return u if u.startswith("http") else urljoin(BASE, u)

    def collect_parts(node) -> List[str]:
        segs: List[str] = []
        from bs4 import NavigableString, Tag
        for child in node.descendants:
            if isinstance(child, Tag) and child.name == "img":
                src = child.get("src") or child.get("data-src") or child.get("data-original")
                if src:
                    segs.append(absolutize(src))
            elif isinstance(child, NavigableString):
                text = child.strip()
                if text:
                    segs.append(text)
        return segs

    content_list = collect_parts(content_node) if content_node else []
    content = "\n".join(content_list)

    return title, date, content


def crawl(limit: int = 20, out: str = "synced.jsonl") -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    list_html = fetch_html(LIST_URL)
    urls = parse_list(list_html)[:limit]
    with open(out, "w", encoding="utf-8") as fp:
        for url in tqdm(urls, desc="Crawling"):
            try:
                title, date, content = fetch_detail(url)
            except Exception as e:
                print("skip", url, e)
                continue

            record = {"url": url, "title": title, "date": date, "content": content}
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(random.uniform(1, 2))

    print(f"Saved {len(urls)} articles into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl SyncedReview homepage")
    parser.add_argument("--limit", type=int, default=20, help="articles to crawl")
    parser.add_argument("--out", default="data/synced.jsonl", help="Output file")
    args = parser.parse_args()

    crawl(args.limit, args.out)

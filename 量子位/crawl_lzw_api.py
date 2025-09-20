"""Crawl qbitai.com home page and save article title + full text.o

The site renders static HTML (WordPress). Each article link in <article>.
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import List

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE = "https://www.qbitai.com"
LIST_URL = BASE + "/"  # 首页
HEADERS = {"User-Agent": "qbitai-crawler/0.1"}


def fetch_html(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_list(html: str) -> List[dict]:
    soup = BeautifulSoup(html, "lxml")
    results = []
    # Prefer explicit title selector (single-post listing)
    for a_tag in soup.select("h2.entry-title a[href]"):
        url = a_tag["href"]
        title = a_tag.get_text(strip=True)
        if not url.startswith("http"):
            url = BASE + url
        results.append({"url": url, "title": title})
    # Fallback to any <article><a>
    if not results:
        for art in soup.select("article"):
            a_tag = art.find("a", href=True)
            if not a_tag:
                continue
            url = a_tag["href"]
            title = a_tag.get_text(strip=True)
            if not url.startswith("http"):
                url = BASE + url
            results.append({"url": url, "title": title})
    # Second fallback: homepage blocks
    if not results:
        for a_tag in soup.select("div.article_list div.picture_text h4 a[href]"):
            url = a_tag["href"]
            title = a_tag.get_text(strip=True)
            if not url.startswith("http"):
                url = BASE + url
            results.append({"url": url, "title": title})
    return results


def fetch_detail(url: str) -> tuple[str, str, str]:
    """Return (title, date, content)"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.select_one("h1.entry-title") or soup.select_one("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    content_node = (
        soup.select_one("div.entry-content")
        or soup.select_one("div.article-content")
        or soup.select_one("div.article__content")
        or soup.select_one("div.article")
    )

    def absolutize(u: str) -> str:
        return u if u.startswith("http") else BASE + u

    def collect_parts(node) -> str:
        segments = []
        for child in node.descendants:
            if getattr(child, "name", None) == "img":
                url = child.get("src") or child.get("data-src") or child.get("data-original")
                if url:
                    segments.append(absolutize(url))
            else:
                txt = BeautifulSoup(str(child), "lxml").get_text(" ", strip=True)
                if txt:
                    segments.append(txt)
        return " ".join(segments).strip()

    if content_node:
        text = collect_parts(content_node)
    else:
        text = ""

    # date extraction: meta tag or span.single_date
    date_meta = soup.select_one('meta[property="article:published_time"]')
    date_span = soup.select_one('span.date') or soup.select_one('span.single_date')
    date = ""
    if date_meta and date_meta.has_attr('content'):
        date = date_meta['content'][:10]
    elif date_span:
        date = date_span.get_text(strip=True)[:10]

    return title, date, text


def crawl(limit: int = 30, out: str = "qbitai_articles.jsonl") -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    list_html = fetch_html(LIST_URL)

    # # DEBUG disabled: save homepage html
    # try:
    #     Path("debug").mkdir(exist_ok=True)
    #     Path("debug/debug_home.html").write_text(list_html, encoding="utf-8")
    # except Exception:
    #     pass

    items = parse_list(list_html)[:limit]

    with open(out, "w", encoding="utf-8") as fp:
        for item in tqdm(items, desc="Crawling"):
            title2, date, content = fetch_detail(item["url"])
            # # DEBUG disabled: save empty content pages
            # if not content:
            #     try:
            #         Path("debug/empty").mkdir(parents=True, exist_ok=True)
            #         fname = item["url"].rstrip("/").split("/")[-1] or "index"
            #         Path(f"debug/empty/{fname}.html").write_text(fetch_html(item["url"]), encoding="utf-8")
            #     except Exception:
            #         pass
            record = {
                "url": item["url"],
                "title": title2 or item["title"],
                "date": date,
                "content": content,
            }
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(random.uniform(1, 2))
    print(f"Saved {len(items)} articles into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl qbitai home page")
    parser.add_argument("--limit", type=int, default=30, help="articles to crawl")
    parser.add_argument("--out", default="data/qbitai.jsonl", help="output file")
    args = parser.parse_args()

    crawl(args.limit, args.out)

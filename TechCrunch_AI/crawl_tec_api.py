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

BASE = "https://techcrunch.com"
# TechCrunch 人工智能分类页
LIST_URL = f"{BASE}/category/artificial-intelligence/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Gecko"}


def fetch_html(url: str, timeout: int = 20) -> str:
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.text


def parse_list(html: str) -> List[str]:
    """返回分类页所有文章链接（顺序）。"""
    soup = BeautifulSoup(html, "lxml")

    links: list[str] = []
    seen: set[str] = set()

    sel = [
        "article a.post-block__title__link",
        "h2.post-block__title a",
        "a.loop-card__title-link",
        "a[data-ga-entry-text]",
    ]

    for css in sel + ["div.post-block a.post-block__title__link"]:
        for a in soup.select(css):
            href = a["href"].split("?", 1)[0]
            if href not in seen:
                links.append(href)
                seen.add(href)

    if not links:
        Path("debug").mkdir(exist_ok=True)
        Path("debug/tech_home.html").write_text(html, encoding="utf-8")
        print("parse_list found 0 links; html saved to debug/tech_home.html")

    return links


def fetch_detail(url: str) -> tuple[str, str, str]:
    """Return (title, date, content) for TechCrunch article"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    content_node = (
        soup.select_one("div.article-content")
        or soup.select_one("div.article__content")
        or soup.select_one("div.entry-content")
    )

    def collect_paragraphs(node) -> str:
        pieces = [p.get_text(" ", strip=True) for p in node.find_all("p") if p.get_text(strip=True)]
        return "\n".join(pieces).strip()

    content = collect_paragraphs(content_node) if content_node else ""

    # date
    date = ""
    time_tag = soup.find("time")
    if time_tag and time_tag.has_attr("datetime"):
        date = time_tag["datetime"][:10]

    return title, date, content


def crawl(limit: int = 30, out: str = "techcrunch_ai.jsonl") -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    list_html = fetch_html(LIST_URL)

    # # DEBUG disabled: save homepage html
    # try:
    #     Path("debug").mkdir(exist_ok=True)
    #     Path("debug/debug_home.html").write_text(list_html, encoding="utf-8")
    # except Exception:
    #     pass

    urls = parse_list(list_html)[:limit]

    with open(out, "w", encoding="utf-8") as fp:
        for url in tqdm(urls, desc="Crawling"):
            try:
                title, date, content = fetch_detail(url)
            except Exception as e:
                print(f"skip {url}: {e}")
                continue

            # # -- debug: 保存正文为空的页面 --
            # if not content:
            #     try:
            #         Path("debug/empty").mkdir(parents=True, exist_ok=True)
            #         fname = url.rstrip("/").split("/")[-1] or "index"
            #         Path(f"debug/empty/{fname}.html").write_text(fetch_html(url), encoding="utf-8")
            #     except Exception:
            #         pass

            record = {"url": url, "title": title, "date": date, "content": content}
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(random.uniform(1, 2))
    print(f"Saved {len(urls)} articles into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl TechCrunch AI category")
    parser.add_argument("--limit", type=int, default=30, help="articles to crawl")
    parser.add_argument("--out", default="data/techcrunch_ai.jsonl", help="output file")
    args = parser.parse_args()

    crawl(args.limit, args.out)

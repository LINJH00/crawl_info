"""Crawl Hugging Face papers trending page and save papers title + abstract.

URL: https://huggingface.co/blog
首页含有多个博客卡片，卡片内的 <a href="/blog/xxx"> 指向具体文章。
进入文章详情页后，标题位于 <h1>，正文位于 <article> 或 div.markdown 内。
保存 JSONL: url,title,content
"""
from __future__ import annotations

import json
import random
import time
from pathlib import Path
from typing import List

import requests
from requests.adapters import HTTPAdapter, Retry
from bs4 import BeautifulSoup
from tqdm import tqdm

BASE = "https://huggingface.co"
LIST_URL = f"{BASE}/blog"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}

# session with retry
session = requests.Session()
retry_cfg = Retry(total=5, backoff_factor=1, status_forcelist=[429, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retry_cfg))


def fetch_html(url: str, timeout: int = 30) -> str:
    for i in range(3):  # extra retries for connection issues
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.text
        except Exception as e:
            if i == 2:
                raise
            print(f"Retry {i+1}/3 for {url}: {e}")
            time.sleep(2)


def parse_list(html: str) -> List[str]:
    """解析博客首页Card，只返回主页卡片里的文章链接，按页面顺序。"""
    soup = BeautifulSoup(html, "lxml")

    links: list[str] = []
    seen: set[str] = set()

    # 1) 优先从首页 BlogThumbnail 卡片结构提取
    for thumb in soup.select("div[data-target='BlogThumbnail']"):
        a = thumb.find("a", href=True)
        if not a:
            continue
        href = a["href"].split("?", 1)[0].split("#", 1)[0]
        if href.rstrip("/") == "/blog":
            continue
        if href not in seen and href.startswith("/blog/"):
            links.append(href)
            seen.add(href)

    # 2) fallback：任何指向 /blog/xxx 的链接
    if not links:
        for a in soup.select("a[href^='/blog/']"):
            href = a["href"].split("?", 1)[0].split("#", 1)[0]
            if href.rstrip("/") == "/blog":
                continue
            if href not in seen:
                links.append(href)
                seen.add(href)

    return [BASE + path for path in links]


def fetch_detail(url: str) -> tuple[str, str]:
    """返回 (title, content)"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 各种正文容器：article、div.markdown、div[data-target="MarkdownRenderer"], div.prose, main > div 等
    content_tag = (
        soup.find("article")
        or soup.find("div", class_="markdown")
        or soup.find("div", attrs={"data-target": "MarkdownRenderer"})
        or soup.find("div", class_="prose")
        or soup.select_one("main div")
    )

    def absolutize(src: str) -> str:
        return src if src.startswith("http") else BASE + src

    if content_tag:
        segments: list[str] = []
        for elem in content_tag.descendants:
            # 图片
            if getattr(elem, "name", None) == "img":
                src = elem.get("src") or elem.get("data-src") or elem.get("data-original")
                if src:
                    segments.append(absolutize(src))
            # 段落/文本
            elif getattr(elem, "name", None) == "p":
                txt = elem.get_text(" ", strip=True)
                if txt:
                    segments.append(txt)
        content = "\n".join(segments).strip()
    else:
        content = ""

    return title, content


def crawl(limit: int = 30, out: str = "hf_papers.jsonl") -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    list_html = fetch_html(LIST_URL)

    # # -- debug: 保存首页 HTML --
    # try:
    #     Path("debug").mkdir(exist_ok=True)
    #     Path("debug/debug_home.html").write_text(list_html, encoding="utf-8")
    # except Exception as e:
    #     print(f"[warn] failed to save debug html: {e}")

    urls = parse_list(list_html)[:limit]

    with open(out, "w", encoding="utf-8") as fp:
        for url in tqdm(urls, desc="Crawling"):
            title, content = fetch_detail(url)
            record = {"url": url, "title": title, "content": content}
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(random.uniform(1, 2))
    print(f"Saved {len(urls)} posts into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl HuggingFace papers trending")
    parser.add_argument("--limit", type=int, default=30, help="Number of papers")
    parser.add_argument("--out", default="data/hf_papers.jsonl", help="Output file")
    args = parser.parse_args()

    crawl(args.limit, args.out)

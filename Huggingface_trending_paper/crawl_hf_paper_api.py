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
# Trending papers 列表页
LIST_URL = f"{BASE}/papers/trending"
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
    """解析 Trending Papers 页面，返回论文详情页完整 URL 按页面顺序。"""
    soup = BeautifulSoup(html, "lxml")

    links: list[str] = []
    seen: set[str] = set()

    # 1) 尝试 card <article> 结构
    for art in soup.select("article"):
        a_tag = art.find("a", href=True)
        if not a_tag:
            continue
        href = a_tag["href"].split("?", 1)[0].split("#", 1)[0]
        if href.startswith("/papers/") and href not in seen:
            links.append(BASE + href)
            seen.add(href)

    # 2) 若仍为空，fallback 任意 <a href="/papers/...">
    if not links:
        for a_tag in soup.select("a[href^='/papers/']"):
            href = a_tag["href"].split("?", 1)[0].split("#", 1)[0]
            if href not in seen:
                links.append(BASE + href)
                seen.add(href)

    return links


def fetch_detail(url: str) -> tuple[str, str]:
    """返回 (title, context=abstract)"""
    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # 论文摘要位于 div.paper-details__abstract
    content_tag = soup.select_one("div.paper-details__abstract")

    def absolutize(src: str) -> str:
        return src if src.startswith("http") else BASE + src

    context = ""
    if content_tag:
        segments: list[str] = []
        for p in content_tag.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if txt:
                segments.append(txt)
        context = "\n".join(segments).strip()

    # fallback: 从 __NEXT_DATA__ 中抽取摘要
    if not context:
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if script_tag and script_tag.string:
            try:
                import json as _json
                nxt = _json.loads(script_tag.string)
                def find_abstract(obj):
                    if isinstance(obj, dict):
                        if "abstract" in obj and isinstance(obj["abstract"], str):
                            return obj["abstract"]
                        for v in obj.values():
                            res = find_abstract(v)
                            if res:
                                return res
                    elif isinstance(obj, list):
                        for v in obj:
                            res = find_abstract(v)
                            if res:
                                return res
                    return ""

                abstract = find_abstract(nxt)
                context = abstract.strip()
            except Exception:
                pass

    # 再次 fallback：根据 "Abstract" 标题定位
    if not context:
        import re
        h2_abs = soup.find("h2", string=re.compile(r"^\s*Abstract\s*$", re.I))
        if h2_abs:
            # 容器在父 div 内，找所有段落
            parent = h2_abs.find_parent()
            if parent:
                paras = [p.get_text(" ", strip=True) for p in parent.find_all("p") if p.get_text(strip=True)]
                context = "\n".join(paras).strip()

    return title, context


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
            title, context = fetch_detail(url)
            # if not context:
            #     # 保存空摘要页面供调试
            #     try:
            #         Path("debug/empty").mkdir(parents=True, exist_ok=True)
            #         fname = url.rstrip("/").split("/")[-1] or "index"
            #         Path(f"debug/empty/{fname}.html").write_text(fetch_html(url), encoding="utf-8")
            #     except Exception as e:
            #         print(f"[warn] failed to save empty page {url}: {e}")

            record = {"url": url, "title": title, "context": context}
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            time.sleep(random.uniform(1, 2))
    print(f"Saved {len(urls)} posts into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl HuggingFace trending papers")
    parser.add_argument("--limit", type=int, default=30, help="Number of papers")
    parser.add_argument("--out", default="data/hf_papers.jsonl", help="Output file")
    args = parser.parse_args()

    crawl(args.limit, args.out)

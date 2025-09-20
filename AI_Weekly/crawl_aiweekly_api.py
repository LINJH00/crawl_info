"""Crawl latest AI Weekly issue (https://aiweekly.co/) and save external article titles + contents.

Usage:
    python crawl_aiweekly_api.py --limit 20 --out data/aiweekly.jsonl

The script performs:
1. Fetch https://aiweekly.co/ home page to locate the first /issues/<id> link (assumed newest issue).
2. Parse that issue page to get publication date and all external article URLs.
3. Visit each external link (up to --limit) and extract title + textual content.
4. Write JSON Lines with fields: url, title, date, content.
"""
from __future__ import annotations

import json
import random
import re
import time
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm
import logging

# optional anti-bot helpers
try:
    import cloudscraper  # type: ignore
except ImportError:
    cloudscraper = None  # noqa: N816

# Playwright is heavy; load lazily only if installed
try:
    from playwright.sync_api import sync_playwright  # type: ignore
except ImportError:
    sync_playwright = None  # noqa: N816


BASE = "https://aiweekly.co"
HOME = BASE + "/"
HEADERS = {"User-Agent": "aiweekly-crawler/0.1 (+https://github.com/)"}


def fetch_html(url: str, timeout: int = 30) -> str:
    """Return HTML with progressive fallbacks: requests → cloudscraper → Playwright.

    1. Standard requests (fast)
    2. cloudscraper for Cloudflare JS challenge (if installed)
    3. Playwright headless browser (if installed)
    """

    # ---------------- requests ----------------
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code == 200 and "verify you are human" not in resp.text.lower():
            return resp.text
        logging.warning("[fetch_html] requests blocked (%s)", resp.status_code)
    except Exception as exc:
        logging.warning("[fetch_html] requests error: %s", exc)

    # ---------------- cloudscraper ----------------
    if cloudscraper is not None:
        try:
            scraper = cloudscraper.create_scraper(
                browser={"custom": "firefox"}, delay=10
            )
            resp = scraper.get(url, headers=HEADERS, timeout=timeout)
            if resp.status_code == 200:
                return resp.text
            logging.warning("[fetch_html] cloudscraper blocked (%s)", resp.status_code)
        except Exception as exc:
            logging.warning("[fetch_html] cloudscraper error: %s", exc)

    # ---------------- Playwright ----------------
    if sync_playwright is None:
        raise RuntimeError(
            "All fetch methods failed and Playwright not installed; cannot bypass protection"
        )

    try:
        with sync_playwright() as p:
            # choose an installed Playwright browser (Firefox→Chromium→WebKit)
            if not p.chromium.executable_path:
                raise RuntimeError("Chromium browser not installed for Playwright; run `playwright install chromium`")

            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_default_navigation_timeout(timeout * 1000)
            page.goto(url, wait_until="domcontentloaded")
            html = page.content()
            browser.close()
            return html
    except Exception as exc:
        raise RuntimeError(f"Playwright failed to fetch {url}: {exc}") from exc


def resolve_redirect(url: str, timeout: int = 15) -> str:
    """Follow redirects for tracking short links (e.g., cur.at) and return final URL."""
    try:
        r = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=timeout)
        final = r.url
        # Occasionally HEAD may be blocked; fallback to GET with stream=True
        if final == url:
            r2 = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=timeout, stream=True)
            final = r2.url
        return final
    except Exception:
        return url


def find_latest_issue_url(home_html: str) -> str:
    """Return newest issue URL.

    Strategy:
    1. Scan homepage for any <a> that contains '/issues/<number>'. Accept absolute or relative links.
    2. If not found, fetch '/issues' archive page and take the first issue link.
    """
    soup = BeautifulSoup(home_html, "lxml")

    # 1) direct search on home page
    for a in soup.find_all("a", href=True):
        href = a["href"].split("?", 1)[0]
        if re.search(r"/issues/\d+", href):
            if not href.startswith("http"):
                href = BASE + href
            return href.rstrip("/")

    # 2) fallback: visit /issues page (issue archive)
    try:
        archive_html = fetch_html(BASE + "/issues")
        soup = BeautifulSoup(archive_html, "lxml")
        first = soup.find("a", href=re.compile(r"/issues/\d+"))
        if first and first.has_attr("href"):
            href = first["href"].split("?", 1)[0]
            if not href.startswith("http"):
                href = BASE + href
            return href.rstrip("/")
    except Exception as exc:
        print(f"[warn] failed to fetch /issues archive: {exc}")

    raise RuntimeError("Latest issue link not found on aiweekly.co")


def parse_issue(issue_html: str) -> tuple[str, List[str]]:
    """Parse issue page and return (date, list_of_external_urls)."""
    soup = BeautifulSoup(issue_html, "lxml")

    # Date extraction
    date_txt = ""
    time_tag = soup.find("time")
    if time_tag and time_tag.get_text(strip=True):
        date_txt = time_tag.get_text(strip=True)
    else:
        m = re.search(r"([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?\s+\d{4})", soup.get_text(" "))
        if m:
            date_txt = m.group(1)

    # Collect external links
    links: list[str] = []
    seen: set[str] = set()

    # iterate through category sections; skip sponsor/powered-by/footer ads
    for section in soup.select("section.category"):
        cls = section.get("class", [])
        if any(c in {"cc-powered-by", "cc-sponsorfooter"} for c in cls):
            continue  # skip advertisement blocks

        for a in section.find_all("a", href=True):
            href = a["href"].strip()
            # Skip internal links
            if href.startswith("/") or "aiweekly.co" in href:
                continue

            # Normalize by去掉查询串和末尾斜杠，避免 sponsor 短链重复
            href_norm = href.split("?", 1)[0].rstrip("/")

            if href_norm in seen:
                continue

            seen.add(href_norm)
            links.append(href)
    return date_txt, links


def extract_article(url: str) -> tuple[str, str]:
    """Generic article extractor returning (title, content)."""
    # Expand tracking short links like cur.at to real destination
    parsed = urlparse(url)
    if parsed.netloc.endswith("cur.at"):
        expanded = resolve_redirect(url)
        if expanded != url:
            url = expanded

    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    title_tag = soup.find("h1") or soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    def absolutize(src: str) -> str:
        if src.startswith("http"):
            return src
        if src.startswith("//"):
            return "https:" + src
        return url.rstrip("/") + "/" + src.lstrip("/")

    # 选取正文容器；若未找到则使用全文
    content_root = (
        soup.find("article")
        or soup.find("main")
        or soup.select_one("div.article-content, div.entry-content")
        or soup
    )

    segments: list[str] = []
    seen_imgs: set[str] = set()

    for elem in content_root.descendants:
        if getattr(elem, "name", None) == "p":
            txt = elem.get_text(" ", strip=True)
            if txt:
                segments.append(txt)
        elif getattr(elem, "name", None) == "img":
            src = elem.get("src") or elem.get("data-src")
            if not src or src.endswith(".svg"):
                continue  # 跳过小图标 / svg
            abs_src = absolutize(src)
            if abs_src not in seen_imgs:
                seen_imgs.add(abs_src)
                segments.append(abs_src)

    content = " \n".join(segments).strip()

    # Skip pages that are actually Cloudflare/human verification placeholders
    if not content or "verify you are human" in content.lower():
        raise ValueError("verification page detected")

    return title, content


def crawl(limit: int = 30, out: str = "aiweekly.jsonl") -> None:
    Path(out).parent.mkdir(parents=True, exist_ok=True)

    home_html = fetch_html(HOME)
    # # -- DEBUG: 保存首页 HTML 便于排查反爬 --
    # try:
    #     Path("debug").mkdir(exist_ok=True)
    #     Path("debug/debug_home.html").write_text(home_html, encoding="utf-8")
    # except Exception:
    #     pass  # 调试辅助，失败可忽略

    latest_issue_url = find_latest_issue_url(home_html)
    issue_html = fetch_html(latest_issue_url)

    # # -- DEBUG: 保存期刊页面 HTML --
    # try:
    #     Path("debug/debug_issue.html").write_text(issue_html, encoding="utf-8")
    # except Exception:
    #     pass

    issue_date, article_urls = parse_issue(issue_html)
    urls = article_urls[:limit]

    saved = 0
    with open(out, "w", encoding="utf-8") as fp:
        for url in tqdm(urls, desc="Crawling"):
            success = False
            for attempt in range(3):
                try:
                    title, content = extract_article(url)
                    success = True
                    break
                except Exception as exc:
                    if attempt == 2:
                        print(f"[warn] skip {url}: {exc}")
                    else:
                        time.sleep(2)  # brief pause before retry
            if not success:
                continue

            record = {"url": url, "title": title, "date": issue_date, "content": content}
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            saved += 1
            time.sleep(random.uniform(1, 2))

    print(f"Saved {saved} / {len(urls)} articles into {out}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crawl the latest AI Weekly issue")
    parser.add_argument("--limit", type=int, default=30, help="Max articles to crawl")
    parser.add_argument("--out", default="data/aiweekly.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    crawl(args.limit, args.out)

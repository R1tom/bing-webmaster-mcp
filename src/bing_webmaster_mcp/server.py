"""Bing Webmaster Tools MCP server (stdio). Set BING_WEBMASTER_API_KEY (Bing Webmaster Tools → Settings → API access →
Generate API Key). Optional INDEXNOW_KEY enables instant submissions through IndexNow.

Hosted version with Google Search Console, Google-vs-Bing gap analysis and one-click OAuth: https://indexpulse.puzaricloud.in"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import httpx
from mcp.server.mcpserver import MCPServer

from .client import Bing, BingError, issue_names

mcp = MCPServer("bing-webmaster", title="Bing Webmaster Tools", version="0.1.0", website_url="https://github.com/R1tom/bing-webmaster-mcp", instructions=(
    "Read Bing Webmaster Tools data and submit URLs to Bing. Start with list_sites; site_url must be a site exactly as Bing lists it "
    "(e.g. https://example.com/). Bing's index also powers ChatGPT search and Microsoft Copilot answers."))
HOSTED = "https://indexpulse.puzaricloud.in"


def _bing() -> Bing:
    key = os.environ.get("BING_WEBMASTER_API_KEY") or os.environ.get("BING_API_KEY")
    if not key:
        raise BingError("Set BING_WEBMASTER_API_KEY. Get it in Bing Webmaster Tools → Settings → API access → Generate API Key. "
                        f"(Or skip the key entirely with the hosted version: {HOSTED})")
    return Bing(api_key=key)


def _date(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date() if s else None
    except ValueError:
        return None


def _agg(rows: list[dict], days: int) -> list[dict]:
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    acc: dict[str, dict] = {}
    for r in rows:
        d = _date(r.get("Date"))
        if d and d < since:
            continue
        a = acc.setdefault(r.get("Query") or "", {"clicks": 0, "impressions": 0, "_p": 0.0, "_w": 0})
        imps = int(r.get("Impressions") or 0)
        a["clicks"] += int(r.get("Clicks") or 0)
        a["impressions"] += imps
        pos = r.get("AvgImpressionPosition")
        if pos not in (None, -1) and imps:
            a["_p"] += float(pos) * imps
            a["_w"] += imps
    out = [{"key": k, "clicks": a["clicks"], "impressions": a["impressions"], "ctr_pct": round(100 * a["clicks"] / a["impressions"], 2) if a["impressions"] else 0,
            "avg_position": round(a["_p"] / a["_w"], 1) if a["_w"] else None} for k, a in acc.items()]
    return sorted(out, key=lambda r: (r["clicks"], r["impressions"]), reverse=True)


@mcp.tool()
def list_sites() -> list[dict]:
    """Sites in your Bing Webmaster Tools account and whether each is verified."""
    return [{"site_url": s.get("Url"), "verified": s.get("IsVerified")} for s in _bing().sites()]


@mcp.tool()
def search_performance(site_url: str, dimension: str = "query", days: int = 28, limit: int = 25) -> list[dict]:
    """Bing clicks, impressions, CTR and average position for top queries (dimension="query") or pages ("page") over the last N days.
    Bing updates these statistics weekly."""
    b = _bing()
    rows = b.page_stats(site_url) if dimension == "page" else b.query_stats(site_url)
    return _agg(rows, max(1, min(480, days)))[: max(1, min(1000, limit))]


@mcp.tool()
def traffic_trend(site_url: str, days: int = 90) -> list[dict]:
    """Daily Bing clicks and impressions for the site."""
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    rows = [{"date": str(_date(x.get("Date"))), "clicks": x.get("Clicks"), "impressions": x.get("Impressions")} for x in _bing().traffic(site_url)
            if _date(x.get("Date")) and _date(x.get("Date")) >= since]
    return sorted(rows, key=lambda r: r["date"])


@mcp.tool()
def crawl_health(site_url: str, days: int = 30) -> dict:
    """Bing crawl statistics (pages crawled, errors, in index, status codes) and crawl issues grouped by type."""
    b = _bing()
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    stats = [x for x in b.crawl_stats(site_url) if _date(x.get("Date")) and _date(x.get("Date")) >= since]
    keys = ("CrawledPages", "CrawlErrors", "Code2xx", "Code301", "Code302", "Code4xx", "Code5xx", "BlockedByRobotsTxt", "ContainsMalware")
    issues: dict[str, list] = {}
    for i in b.crawl_issues(site_url):
        for name in issue_names(i.get("Issues")) or ["Other"]:
            issues.setdefault(name, []).append({"url": i.get("Url"), "http_code": i.get("HttpCode"), "inbound_links": i.get("InLinks")})
    latest = max(stats, key=lambda x: x.get("Date") or "", default={})
    return {"totals": {k: sum(int(x.get(k) or 0) for x in stats) for k in keys}, "pages_in_index": latest.get("InIndex"),
            "issues": {k: {"count": len(v), "examples": v[:15]} for k, v in issues.items()}}


@mcp.tool()
def url_info(site_url: str, url: str) -> dict:
    """Whether Bing knows a URL: discovery date, last crawl, HTTP status, inbound links and its Bing clicks/impressions."""
    b = _bing()
    info = b.url_info(site_url, url) or {}
    try:
        tr = b.url_traffic(site_url, url) or {}
    except BingError:
        tr = {}
    return {"url": url, "known_to_bing": bool(info.get("LastCrawledDate") or info.get("DiscoveryDate")), "last_crawled": info.get("LastCrawledDate"),
            "discovered": info.get("DiscoveryDate"), "http_status": info.get("HttpStatus"), "inbound_links": info.get("AnchorCount"),
            "clicks": tr.get("Clicks"), "impressions": tr.get("Impressions")}


@mcp.tool()
def sitemaps(site_url: str) -> list[dict]:
    """Sitemaps and feeds Bing knows for the site, with status, URL count and last crawl."""
    return [{"sitemap": s.get("Url"), "status": s.get("Status"), "urls": s.get("UrlCount"), "submitted": s.get("Submitted"), "last_crawled": s.get("LastCrawled")}
            for s in _bing().feeds(site_url)]


@mcp.tool()
def submit_sitemap(site_url: str, sitemap_url: str) -> str:
    """Submit or resubmit a sitemap to Bing."""
    _bing().submit_feed(site_url, sitemap_url)
    return f"Submitted {sitemap_url} to Bing."


@mcp.tool()
def submit_urls(site_url: str, urls: list[str]) -> dict:
    """Ask Bing to crawl up to 500 URLs now (Bing URL Submission API, daily quota). If INDEXNOW_KEY is set, the URLs also go to
    IndexNow (Bing, Yandex, Seznam, Naver, Yep)."""
    b = _bing()
    urls = urls[:500]
    out: dict = {}
    q = b.quota(site_url)
    left = int(q.get("DailyQuota") or 0)
    send = urls[:left]
    if send:
        b.submit_urls(site_url, send)
    out["bing"] = {"submitted": len(send), "daily_quota_left": left - len(send), "not_sent": len(urls) - len(send)}
    key = os.environ.get("INDEXNOW_KEY")
    if key and urls:
        host = urlsplit(urls[0]).hostname
        r = httpx.post("https://api.indexnow.org/indexnow", json={"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": urls}, timeout=30)
        out["indexnow"] = {"status": r.status_code, "ok": r.status_code in (200, 202)}
    return out


@mcp.tool()
def backlinks(site_url: str, url: str = "", page: int = 0) -> dict:
    """Pages on the site with inbound links (counts), or the linking pages and anchors for one URL."""
    b = _bing()
    if url:
        d = b.url_links(site_url, url, page)
        return {"total_pages": d.get("TotalPages"), "links": [{"from": x.get("Url"), "anchor": x.get("AnchorText")} for x in d.get("Details") or []]}
    d = b.link_counts(site_url, page)
    return {"total_pages": d.get("TotalPages"), "pages": [{"url": x.get("Url"), "inbound_links": x.get("Count")} for x in d.get("Links") or []]}


@mcp.tool()
def keyword_research(keyword: str, country: str = "us", language: str = "en-US") -> list[dict]:
    """Bing weekly search impressions (exact and broad match) for a keyword in a country and language."""
    rows = _bing().keyword_stats(keyword, country.lower(), language)
    return sorted(({"week": str(_date(x.get("Date"))), "exact": x.get("Impressions"), "broad": x.get("BroadImpressions")} for x in rows), key=lambda r: r["week"])


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

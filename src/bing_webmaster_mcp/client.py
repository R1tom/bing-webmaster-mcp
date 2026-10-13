"""Bing Webmaster Tools JSON API client (shared with the hosted IndexPulse service). Calls look like
GET  {BING_API_BASE}/GetQueryStats?siteUrl=...&apikey=...
POST {BING_API_BASE}/SubmitUrlBatch?apikey=...   body {"siteUrl": ..., "urlList": [...]}
Responses wrap the payload in {"d": ...}; dates come as "/Date(1700000000000)/" or "/Date(1700000000000-0700)/".
With OAuth the token goes in an Authorization: Bearer header instead of ?apikey=."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

import httpx

import os

API_BASE = os.environ.get("BING_API_BASE", "https://ssl.bing.com/webmaster/api.svc/json").rstrip("/")
_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")
TIMEOUT = 25


class BingError(Exception):
    def __init__(self, message: str, code: str = "error", status: int = 0):
        super().__init__(message)
        self.code, self.status = code, status


def _conv(v):
    if isinstance(v, str):
        m = _DATE.match(v)
        if m:
            ms = int(m.group(1))
            if ms <= 0:
                return None
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        return v
    if isinstance(v, list):
        return [_conv(x) for x in v]
    if isinstance(v, dict):
        return {k: _conv(x) for k, x in v.items() if k != "__type"}
    return v


# ApiErrorCode enum of the Bing Webmaster API.
_ERRORS = {
    1: ("internal", "Bing returned an internal error. Try again shortly."),
    2: ("unknown", "Bing returned an unknown error. Try again shortly."),
    3: ("invalid_api_key", "Bing rejected the API key. Generate a new one in Bing Webmaster Tools → Settings → API access and reconnect."),
    4: ("throttled", "Bing is rate-limiting this account. Try again in a minute."),
    5: ("throttled", "Bing is rate-limiting requests for this site. Try again in a minute."),
    6: ("blocked", "Bing has blocked this Bing Webmaster account."),
    7: ("invalid_url", "Bing says that URL is malformed or not part of this site."),
    8: ("invalid_parameter", "Bing rejected a parameter."),
    9: ("too_many_sites", "The Bing account has too many sites."),
    10: ("user_not_found", "Bing doesn't recognise this Bing Webmaster user."),
    11: ("not_found", "Bing has no data for that."),
    12: ("exists", "That already exists in Bing Webmaster Tools."),
    13: ("not_allowed", "Bing doesn't allow that for this site (for URL submissions this usually means today's quota is used up)."),
    14: ("not_authorized", "This Bing Webmaster account can't access that site. Check that the site is added and verified in Bing Webmaster Tools."),
    15: ("unexpected_state", "Bing reported an unexpected state. Try again later."),
    16: ("deprecated", "Bing has retired this API method."),
}


class Bing:
    def __init__(self, *, api_key: str | None = None, access_token: str | None = None, client: httpx.Client | None = None, retries: int = 3):
        if not api_key and not access_token:
            raise BingError("Bing is not connected.", "not_connected")
        self.api_key, self.access_token = api_key, access_token
        self._client = client
        self.retries = retries

    def _request(self, verb: str, method: str, params: dict | None = None, body: dict | None = None):
        q = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        else:
            q["apikey"] = self.api_key
        url = f"{API_BASE}/{method}"
        try:
            h = self._client or httpx.Client(timeout=TIMEOUT)
            try:
                if verb == "GET":
                    r = h.get(url, params=q, headers=headers)
                else:
                    r = h.post(url, params=q, json=body or {}, headers={**headers, "Content-Type": "application/json; charset=utf-8"})
            finally:
                if self._client is None:
                    h.close()
        except httpx.TimeoutException:
            raise BingError("Bing Webmaster API timed out.", "timeout")
        except httpx.HTTPError as e:
            raise BingError(f"Could not reach the Bing Webmaster API ({e.__class__.__name__}).", "network")
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code >= 400 or (isinstance(data, dict) and "ErrorCode" in data):
            code_num = data.get("ErrorCode") if isinstance(data, dict) else None
            code, text = _ERRORS.get(code_num, ("error", ""))
            if r.status_code == 401 and code == "error":
                code, text = _ERRORS[3]
            msg = (data or {}).get("Message") if isinstance(data, dict) else None
            raise BingError(text or f"Bing returned HTTP {r.status_code}{': ' + msg if msg else ''}.", code, r.status_code)
        if isinstance(data, dict) and "d" in data:
            return _conv(data["d"])
        return _conv(data)

    def get(self, method: str, **params):
        """GET with backoff when Bing throttles (ThrottleUser/ThrottleHost): waits 2 s, 4 s, 8 s (up to self.retries times)."""
        for attempt in range(self.retries + 1):
            try:
                return self._request("GET", method, params)
            except BingError as e:
                if e.code != "throttled" or attempt == self.retries:
                    raise
                time.sleep(2 ** (attempt + 1))

    def post(self, method: str, body: dict):
        return self._request("POST", method, None, body)

    # --- typed helpers -------------------------------------------------------------------------------------------
    def sites(self) -> list[dict]:
        return self.get("GetUserSites") or []

    def query_stats(self, site: str) -> list[dict]:
        return self.get("GetQueryStats", siteUrl=site) or []

    def page_stats(self, site: str) -> list[dict]:
        return self.get("GetPageStats", siteUrl=site) or []

    # Bing's samples pass these string parameters JSON-quoted (query=%22q%22), unlike siteUrl.
    def query_page_stats(self, site: str, query: str) -> list[dict]:
        return self.get("GetQueryPageStats", siteUrl=site, query=json.dumps(query)) or []

    def page_query_stats(self, site: str, page: str) -> list[dict]:
        return self.get("GetPageQueryStats", siteUrl=site, page=json.dumps(page)) or []

    def traffic(self, site: str) -> list[dict]:
        return self.get("GetRankAndTrafficStats", siteUrl=site) or []

    def crawl_stats(self, site: str) -> list[dict]:
        return self.get("GetCrawlStats", siteUrl=site) or []

    def crawl_issues(self, site: str) -> list[dict]:
        return self.get("GetCrawlIssues", siteUrl=site) or []

    def url_info(self, site: str, url: str) -> dict | None:
        return self.get("GetUrlInfo", siteUrl=site, url=url)

    def url_traffic(self, site: str, url: str) -> dict | None:
        return self.get("GetUrlTrafficInfo", siteUrl=site, url=url)

    def quota(self, site: str) -> dict:
        return self.get("GetUrlSubmissionQuota", siteUrl=site) or {}

    def submit_urls(self, site: str, urls: list[str]):
        return self.post("SubmitUrlBatch", {"siteUrl": site, "urlList": urls})

    def feeds(self, site: str) -> list[dict]:
        return self.get("GetFeeds", siteUrl=site) or []

    def submit_feed(self, site: str, feed: str):
        return self.post("SubmitFeed", {"siteUrl": site, "feedUrl": feed})

    def link_counts(self, site: str, page: int = 0) -> dict:
        return self.get("GetLinkCounts", siteUrl=site, page=page) or {}

    def url_links(self, site: str, link: str, page: int = 0) -> dict:
        return self.get("GetUrlLinks", siteUrl=site, link=link, page=page) or {}

    def keyword_stats(self, q: str, country: str = "", language: str = "") -> list[dict]:
        return self.get("GetKeywordStats", q=q, country=country, language=language) or []


CRAWL_ISSUE_FLAGS = {
    1: "Code301", 2: "Code302", 4: "Code4xx", 8: "Code5xx", 16: "BlockedByRobotsTxt", 32: "ContainsMalware",
    64: "ImportantUrlBlockedByRobotsTxt", 128: "DnsErrors", 256: "TimeOutErrors",
}


def issue_names(flags) -> list[str]:
    try:
        f = int(flags or 0)
    except (TypeError, ValueError):
        return [str(flags)]
    return [name for bit, name in CRAWL_ISSUE_FLAGS.items() if f & bit] or ([] if f == 0 else [f"flags {f}"])

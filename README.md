# Bing Webmaster Tools MCP server

An [MCP](https://modelcontextprotocol.io) server that lets Claude, Cursor, VS Code and other AI assistants read your **Bing Webmaster Tools** data and ask Bing to crawl your pages.

Why Bing? ChatGPT search and Microsoft Copilot answer from Bing's index. If Bing hasn't crawled a page, those assistants can't cite it, and most sites never look at Bing at all.

> **Want this without installing anything, plus Google Search Console?** [IndexPulse](https://indexpulse.puzaricloud.in) is the hosted version: sign in once with OAuth in Claude or ChatGPT, and get Google + Bing side by side, Google-vs-Bing gap analysis, sitemap indexing checks across both engines, and an AI-crawler audit. Free for one site.

## Tools

| Tool | What it does |
|---|---|
| `list_sites` | Sites in your Bing Webmaster account and their verification status |
| `search_performance` | Clicks, impressions, CTR and average position for top queries or pages |
| `traffic_trend` | Daily clicks and impressions |
| `crawl_health` | Pages crawled, crawl errors, status-code mix, pages in index, crawl issues by type |
| `url_info` | Whether Bing knows a URL: discovered, last crawled, HTTP status, inbound links, traffic |
| `sitemaps` | Sitemaps Bing knows, with status and URL counts |
| `submit_sitemap` | Submit or resubmit a sitemap |
| `submit_urls` | Ask Bing to crawl up to 500 URLs now (daily quota), plus IndexNow if `INDEXNOW_KEY` is set |
| `backlinks` | Pages with inbound links, or the links and anchors for one URL |
| `keyword_research` | Bing weekly search volume for a keyword, by country and language |

## Setup

1. In [Bing Webmaster Tools](https://www.bing.com/webmasters/), add and verify your site (you can import it from Google Search Console).
2. Settings (gear icon) → **API access** → **API Key** → **Generate API Key**.
3. Add the server to your AI app. It needs [uv](https://docs.astral.sh/uv/).

**Claude Desktop / Cursor / VS Code** (`claude_desktop_config.json`, `.cursor/mcp.json`, …):

```json
{
  "mcpServers": {
    "bing-webmaster": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/R1tom/bing-webmaster-mcp", "bing-webmaster-mcp"],
      "env": { "BING_WEBMASTER_API_KEY": "your-key" }
    }
  }
}
```

**Claude Code:**

```sh
claude mcp add bing-webmaster -e BING_WEBMASTER_API_KEY=your-key -- uvx --from git+https://github.com/R1tom/bing-webmaster-mcp bing-webmaster-mcp
```

Optional: set `INDEXNOW_KEY` to a key your site serves at `https://your-site/<key>.txt` to send `submit_urls` through [IndexNow](https://www.indexnow.org/) too (Bing, Yandex, Seznam, Naver, Yep).

## Things to ask

- "Which of my pages has Bing never crawled?" (use `url_info` on pages from your sitemap)
- "What are my top Bing queries this month, and where am I on page 2?"
- "Any crawl errors on example.com? Which broken pages have the most inbound links?"
- "Submit my five newest blog posts to Bing."

## Notes

- The API key is a full-account credential for your Bing Webmaster account; it stays on your machine in the MCP config.
- Bing updates query and page statistics weekly; traffic and crawl statistics daily.
- Bing rate-limits per site; the client backs off and retries automatically.

## License

MIT. Built by [PuzariCloud](https://puzaricloud.in).

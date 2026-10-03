---
name: twitter-scraper
description: Scrape and research Twitter/X posts, monitor accounts, and analyze trends using the tweetytweets autonomous browser engine (MIT). Zero API keys, zero paid scrapers.
version: "1.0.0"
author: SkillForge & tweetytweets
license: MIT
capabilities:
  - Search and scrape Twitter/X tweets without official API keys
  - Extract tweet text, authors, metrics (likes, reposts, replies, views), and timestamps
  - Scrape specific user handles (@username)
  - Research trends across X, Hacker News, and Reddit
  - High-risk publishing gate for sending tweets (requires human approval)
tools:
  - twitter_search
  - twitter_user_tweets
  - twitter_research_trends
  - twitter_post_tweet
  - twitter_status
execution_timeout: 30
---

# Twitter / X Scraper Skill (Powered by tweetytweets)

## Purpose
Scrape, monitor, and research X/Twitter discussions without paying for expensive X API tiers ($100-$5000/mo) or brittle third-party proxy services.

Integrated directly from [vedantdhande04/tweetytweets](https://github.com/vedantdhande04/tweetytweets) (MIT License):
- **Chrome DevTools Protocol (CDP)** over `websockets` directly to Chrome's debugging port (`9222`)
- **No Selenium / No Playwright** — ultra-lightweight stdlib + websockets
- **DuckDuckGo CAPTCHA-free site search fallback** when browser is offline
- **Gemma 4 agent workflow** compatible

## Available Tools

| Tool | Risk Level | Description |
|------|------------|-------------|
| `twitter_search` | LOW | Search X for keywords or hashtags (`query`, `count`, `mode`) |
| `twitter_user_tweets` | LOW | Scrape recent posts from any handle (`handle`, `count`) |
| `twitter_research_trends` | LOW | Multi-source trend gathering across X, HN, and Reddit |
| `twitter_post_tweet` | **HIGH** | Post a tweet (Requires explicit human approval gate) |
| `twitter_status` | LOW | Check Chrome CDP connection status on port 9222 |

## Security & Approval Gate
Any action that writes to Twitter (`twitter_post_tweet`) is classified as `RiskLevel.HIGH` by SkillForge's Policy Engine:
1. The orchestrator halts execution before posting
2. Generates an approval request on the SSE stream
3. Appends the approval decision to the SHA-256 tamper-evident ledger
4. Executes only if approved by the user

## Fallback Strategy
1. **Live CDP Mode**: If Chrome is running on port 9222 (`python tweetytweets/scripts/browser.py launch`), extracts directly from the live DOM.
2. **Public Web Scraper Fallback**: If browser is not logged in or headless, scrapes live public tweets via DuckDuckGo Lite without CAPTCHAs.
3. **Demo Mode**: If `SKILLFORGE_DEMO=true`, returns realistic simulated agent tweets.

---
name: webpage-reader
description: Extract clean, readable text content from any public webpage URL.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Fetch and parse HTML pages
  - Strip markup and extract plain text
  - Handle redirects and encoding
tools:
  - webpage_reader
execution_timeout: 15
---

# Webpage Reader Skill

## Purpose
Fetches a public webpage and returns clean extracted text.
Used after `web-search` or `job-search` to read full page content.

## Examples
- Open and read a job listing URL
- Extract article text from a news page
- Read documentation from a public URL

## Notes
- Read-only; never interacts with forms or logins
- Respects public access only
- Risk level: LOW

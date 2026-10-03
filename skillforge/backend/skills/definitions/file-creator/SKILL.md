---
name: file-creator
description: Create structured files and reports in markdown, text, or JSON from agent-generated content.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Create markdown reports
  - Create plain text files
  - Create JSON output files
  - Save to configurable output directory
tools:
  - create_file
execution_timeout: 5
---

# File Creator Skill

## Purpose
Saves agent-generated content to a file in the output directory.
Used as the final step in research and report-generation workflows.

## Examples
- Save an interview preparation report as markdown
- Create a job requirements summary file
- Export search results as JSON

## Notes
- Files are written to the local `output/` directory
- Risk level: MEDIUM (creates files on disk)
- No network access; purely local operation

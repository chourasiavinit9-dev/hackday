---
name: job-search
description: Search public job listings, extract requirements, and generate interview preparation reports.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Search public job boards (LinkedIn, Naukri, etc.)
  - Extract job requirements and responsibilities
  - Extract interview questions from listing descriptions
  - Group interview questions by topic
  - Generate structured preparation reports
tools:
  - job_search
  - webpage_reader
  - extract_interview_questions
  - create_file
execution_timeout: 60
---

# Job Search Skill

## Purpose
Helps users find relevant job listings, understand requirements, and
prepare for interviews by extracting and grouping interview questions.

## Usage
Describe the job role and optionally a location. The skill searches
public job boards, reads listing content, extracts interview questions,
groups them by topic, and creates a preparation report.

## Examples
- "Find Python data science jobs with interview preparation"
- "Search for ML engineer roles in Bangalore"
- "Find backend developer jobs and extract interview questions"

## Notes
- Does NOT submit applications automatically (by design)
- Only reads publicly available listing content
- Output is saved as a markdown report file
- Risk level: LOW (read-only)

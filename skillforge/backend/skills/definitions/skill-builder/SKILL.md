---
name: skill-builder
description: Generate, validate, and install new SKILL.md-based capabilities using Gemma 4.
version: "1.0.0"
author: SkillForge
license: Apache-2.0
capabilities:
  - Generate SKILL.md from natural language description
  - Validate skill against Agent Skill Open Standard
  - Install validated skills into the local registry
  - Immediately make new skills available for discovery
tools:
  - skill_validate
  - skill_install
execution_timeout: 30
---

# Skill Builder Skill

## Purpose
Allows users to teach SkillForge new capabilities at runtime.
Describe a capability in plain English and Gemma 4 generates a
compliant SKILL.md that is immediately validated and installed.

## Workflow
```
Describe skill (natural language)
    ↓
Gemma 4 generates SKILL.md
    ↓
Validator checks compliance
    ↓
Install to local registry
    ↓
Skill is immediately discoverable
```

## Examples
- "Create a skill that searches research papers on arxiv"
- "Build a skill for finding GitHub repositories by topic"
- "Make a skill that reads PDF documents"

## Notes
- Generated skills use existing tools from the tool registry
- New skills do NOT add new tools automatically (tools must be registered separately)
- Every generated skill is validated before installation
- Risk level: MEDIUM (writes files to disk)

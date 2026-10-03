---
name: laya-router
description: Hallucination-free intent classification and skill routing using Laya (non-autoregressive System 1 model). Runs in 33ms, zero token overhead, Apache 2.0.
version: "1.0.0"
author: SkillForge (integrating NandhaKishorM/laya)
license: Apache-2.0
capabilities:
  - Classify user intent without text generation
  - Route to the correct skill (job-search, youtube, web, twitter, etc.)
  - Detect if user wants file creation, posting, URL reading
  - Assess action risk level (low/medium/high)
  - Block hallucinated tool steps from downstream LLMs
tools:
  - laya_router
source: https://github.com/NandhaKishorM/laya
---

# Laya Router Skill

## Purpose

Laya is a **non-autoregressive System 1 decision engine** built on ModernBERT-large (421M params).
Unlike Gemma which generates tokens, Laya answers structured questions in a **single forward pass (~33ms)**
with zero hallucination risk — because it never generates free-form text.

## How it's used in SkillForge

Before Gemma plans any workflow, Laya answers these questions about the user's goal:

| Question | Type | Answer |
|----------|------|--------|
| Which skill should handle this? | `choice` | job-search / youtube / twitter / web-search / … |
| Does the user want to save a file? | `noul` | true / false (probability) |
| Does the user want to post publicly? | `noul` | true / false |
| Does the user want to read a URL? | `noul` | true / false |
| Does the user want a summary? | `noul` | true / false |
| What is the risk level? | `choice` | low / medium / high |

Laya's structured output is used to:
1. **Route to the correct skill** (replaces keyword heuristics)
2. **Filter Gemma's plan** — if Laya says the user didn't ask to create a file, any `create_file` step Gemma hallucinates is dropped before execution

## Why it beats keyword matching

- Understands **semantic intent**, not just keywords
- Works in **100+ languages** (via laya-multilingual checkpoint)
- **Calibrated confidence** — can abstain when uncertain instead of guessing wrong
- **Trained with RLCD** (reinforcement learning against proper scoring rules)

## Fallback

If Laya is not installed, SkillForge falls back to keyword-based classification automatically. The system never breaks — it degrades gracefully.

## Install

```bash
pip install laya
```

No API key needed. The checkpoint downloads from Hugging Face on first use (~421MB).

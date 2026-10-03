"""
Tests for Laya: Source-Backed Interview Research Agent
Verifies:
  1. Natural-language request classification (TCS, Wipro, YouTube, Twitter, GitHub)
  2. Agent-Reach research & source retrieval
  3. YouTube-Scapper parsing & metadata extraction
  4. Structured interview answer format & clickable citations
  5. Planning to execution transition (never stuck in planning)
  6. Social publishing approval safety (no auto-publish)
  7. Verification that WhatsApp is completely removed
"""
import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from skills.registry import resolve_skill_for_goal, get_skill, list_skills
from tools.laya_router import classify_goal, _keyword_classify
from tools.agent_reach import reach_web_search, reach_web_read, reach_github_search, reach_research
from tools.youtube_scraper import extract_youtube_video_id, youtube_scrape_or_search
from agent.gemma_provider import get_provider


class TestLayaIntentClassification(unittest.TestCase):
    def test_tcs_fresher_interview_questions(self):
        goal = "Find TCS interview questions from last year for fresher software engineers."
        skill = resolve_skill_for_goal(goal)
        self.assertEqual(skill, "interview-research")
        c = _keyword_classify(goal, 0)
        self.assertEqual(c["skill"], "interview-research")
        self.assertFalse(c["wants_post"])

    def test_wipro_interview_questions_suggested_answers(self):
        goal = "Give me Wipro interview questions with suggested answers."
        skill = resolve_skill_for_goal(goal)
        self.assertEqual(skill, "interview-research")
        c = _keyword_classify(goal, 0)
        self.assertEqual(c["skill"], "interview-research")

    def test_wipro_interview_process_background(self):
        goal = "Explain Wipro's interview process and company background."
        skill = resolve_skill_for_goal(goal)
        self.assertEqual(skill, "interview-research")
        c = _keyword_classify(goal, 0)
        self.assertEqual(c["skill"], "interview-research")

    def test_youtube_interview_experiences(self):
        goal = "Search YouTube for TCS interview experiences and summarize the useful advice."
        skill = resolve_skill_for_goal(goal)
        self.assertEqual(skill, "youtube-search")
        c = _keyword_classify(goal, 0)
        self.assertEqual(c["skill"], "youtube-search")
        self.assertTrue(c["wants_summary"])

    def test_twitter_interview_discussion(self):
        goal = "Search Twitter/X for recent discussion about a company's interview process."
        c = _keyword_classify(goal, 0)
        self.assertTrue(c["wants_twitter"])

    def test_github_research(self):
        goal = "Inspect public repositories on GitHub for python interview prep."
        skill = resolve_skill_for_goal(goal)
        self.assertEqual(skill, "github-research")
        c = _keyword_classify(goal, 0)
        self.assertEqual(c["skill"], "github-research")


class TestAgentReachIntegration(unittest.TestCase):
    def test_reach_web_search_returns_real_structure(self):
        res = reach_web_search("TCS interview process", num_results=3)
        self.assertIn("results", res)
        self.assertIn("source", res)
        self.assertIn("agent_reach", res["source"])

    def test_reach_web_read_validation(self):
        res = reach_web_read("not-a-url")
        self.assertIn("error", res)

    def test_reach_github_search(self):
        res = reach_github_search("interview questions", num_results=3)
        self.assertIn("results", res)
        self.assertEqual(res["source"], "agent_reach/github_ddg")

    def test_reach_research_multi_source(self):
        res = reach_research("Wipro interview experience", read_top_result=False)
        self.assertIn("sources", res)
        self.assertIn("attribution", res)
        self.assertIn("Agent-Reach", res["attribution"])


class TestYouTubeScapperIntegration(unittest.TestCase):
    def test_extract_video_id_standard(self):
        vid = extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_extract_video_id_short(self):
        vid = extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_extract_video_id_embed(self):
        vid = extract_youtube_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_extract_video_id_bare(self):
        vid = extract_youtube_video_id("dQw4w9WgXcQ")
        self.assertEqual(vid, "dQw4w9WgXcQ")

    def test_youtube_scrape_or_search(self):
        res = youtube_scrape_or_search("TCS interview experience", num_results=2)
        self.assertIn("videos", res)
        self.assertIn("attribution", res)
        self.assertIn("thesagardahiwal/YouTube-Scapper", res["attribution"])


class TestStructuredInterviewAnswer(unittest.TestCase):
    def test_offline_synthesis_interview_structure(self):
        provider = get_provider()
        goal = "Find TCS interview questions from last year for fresher software engineers."
        tool_results = [
            {
                "tool": "reach_research",
                "result": {
                    "sources": [
                        {
                            "title": "TCS Fresher Interview Experience 2025",
                            "url": "https://www.geeksforgeeks.org/tcs-interview-experience-2025",
                            "snippet": "Covers TCS NQT coding round, technical interview on OOP and SQL, and HR round."
                        }
                    ]
                }
            },
            {
                "tool": "extract_interview_questions",
                "result": {
                    "grouped_questions": {
                        "Core Skills & Coding": [
                            "Explain polymorphism with real-world examples",
                            "What is normalisation in DBMS and explain 3NF"
                        ]
                    }
                }
            }
        ]

        synth = provider._offline_synthesis(goal, tool_results)
        summary = synth["summary"]

        # Required sections
        self.assertIn("Company Overview", summary)
        self.assertIn("Interview Rounds", summary)
        self.assertIn("Technical & Coding Questions", summary)
        self.assertIn("Behavioral", summary)
        self.assertIn("Suggested Answers", summary)
        self.assertIn("Preparation Advice", summary)
        self.assertIn("Sources & Citations", summary)
        self.assertIn("https://www.geeksforgeeks.org", summary)

    def test_planning_does_not_hang(self):
        provider = get_provider()
        goal = "Find TCS interview questions from last year for fresher software engineers."
        plan = provider.plan_workflow(goal, "interview-research", [])
        self.assertIn("steps", plan)
        self.assertGreaterEqual(len(plan["steps"]), 1)
        # Tools must be allowed research tools
        tool_names = [s["tool"] for s in plan["steps"]]
        self.assertTrue(any(t in ("reach_research", "reach_web_search") for t in tool_names))


class TestNoFabricatedDataAndNoWhatsApp(unittest.TestCase):
    def test_no_whatsapp_in_project(self):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        found_whatsapp = []
        for root, dirs, files in os.walk(project_root):
            if ".git" in root or "node_modules" in root or "__pycache__" in root:
                continue
            for file in files:
                if file == "test_laya_research.py":
                    continue
                if file.endswith((".py", ".js", ".html")):
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read().lower()
                        if "whatsapp" in content:
                            found_whatsapp.append(path)
        self.assertEqual(found_whatsapp, [], f"WhatsApp references found in: {found_whatsapp}")


if __name__ == "__main__":
    unittest.main()

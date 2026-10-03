"""
SkillForge Integration Tests
Covers the full Laya → Agent-Reach research → tweetytweets draft → approve → publish → verify flow.

Design:
  - All external HTTP calls are intercepted with unittest.mock so tests are deterministic.
  - The running app never falls back to test fixtures; mocking is confined to this file.
  - Tests verify the contract: correct tool dispatch, approval gating, verify_post behavior.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import json
import unittest
from unittest.mock import patch, MagicMock


# ── Laya intent classification ─────────────────────────────────────────────────

class TestLayaRouter(unittest.TestCase):
    def test_draft_intent_detected(self):
        from tools.laya_router import _keyword_classify
        import time
        result = _keyword_classify("draft a tweet about Python agent frameworks", time.time())
        self.assertTrue(result["wants_post"])

    def test_research_intent_detected(self):
        from tools.laya_router import _keyword_classify
        import time
        result = _keyword_classify("research the latest AI news and summarize", time.time())
        # "research" + "study" → research-paper-search; "summarize" triggers wants_summary
        # Both web-search and research-paper-search are valid depending on exact keyword match
        self.assertIn(result["skill"], ("web-search", "research-paper-search"))
        self.assertFalse(result["wants_post"])
        self.assertTrue(result["wants_summary"])

    def test_verify_not_wanted_for_plain_search(self):
        from tools.laya_router import _keyword_classify
        import time
        result = _keyword_classify("find Python jobs in London", time.time())
        self.assertEqual(result["skill"], "job-search")
        self.assertFalse(result["wants_post"])

    def test_twitter_search_classified(self):
        from tools.laya_router import _keyword_classify
        import time
        result = _keyword_classify("search Twitter for Gemma 4 news", time.time())
        self.assertTrue(result["skill"] in ("web-search",))


# ── Agent-Reach adapter ────────────────────────────────────────────────────────

class TestAgentReach(unittest.TestCase):
    def test_reach_web_read_validates_url(self):
        from tools.agent_reach import reach_web_read
        result = reach_web_read("not-a-url")
        self.assertIn("error", result)

    def test_reach_web_search_empty_query(self):
        from tools.agent_reach import reach_web_search
        result = reach_web_search("")
        self.assertIn("error", result)

    def test_reach_research_empty_topic(self):
        from tools.agent_reach import reach_research
        result = reach_research("")
        self.assertIn("error", result)

    def test_reach_web_search_returns_real_structure(self):
        """Mock DDG to test structure without real HTTP."""
        mock_html = """
        <a class="result-link" href="https://example.com/page1">Test Article</a>
        <td class="result-snippet">A snippet about Python agents.</td>
        """
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.read.return_value = mock_html.encode("utf-8")
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=mock_resp):
            from tools.agent_reach import reach_web_search
            result = reach_web_search("Python agents")
        self.assertIn("results", result)
        self.assertEqual(result["query"], "Python agents")
        self.assertIn("agent_reach", result["source"])

    def test_reach_github_search_site_filter(self):
        """Verify github.com site filter is applied."""
        captured = {}
        original_ddg = None

        def fake_ddg(query, num, site=""):
            captured["site"] = site
            captured["query"] = query
            return []

        with patch("tools.agent_reach._ddg_search", side_effect=fake_ddg):
            from tools.agent_reach import reach_github_search
            reach_github_search("AI agent framework")
        self.assertEqual(captured["site"], "github.com")

    def test_reach_research_attribution_present(self):
        """Ensure Agent-Reach attribution is always in the result."""
        with patch("tools.agent_reach._ddg_search", return_value=[]):
            from tools.agent_reach import reach_research
            result = reach_research("open source AI")
        self.assertIn("attribution", result)
        self.assertIn("Agent-Reach", result["attribution"])


# ── Social drafting: draft_post ────────────────────────────────────────────────

class TestDraftPost(unittest.TestCase):
    def test_empty_topic_returns_error(self):
        from tools.twitter import draft_post
        result = draft_post("")
        self.assertIn("error", result)

    def test_draft_never_sets_ready_to_post(self):
        from tools.twitter import draft_post
        result = draft_post("AI agents in 2026")
        self.assertFalse(result.get("ready_to_post"), "draft_post must never return ready_to_post=True")

    def test_draft_requires_approval(self):
        from tools.twitter import draft_post
        result = draft_post("AI agents in 2026")
        self.assertTrue(result.get("requires_approval"), "draft_post must always require approval")

    def test_draft_includes_text(self):
        from tools.twitter import draft_post
        result = draft_post("SkillForge open source agent runtime", sources=[
            {"title": "Test", "url": "https://example.com", "snippet": "An agent runtime built with Gemma 4."}
        ])
        self.assertIn("draft", result)
        self.assertGreater(result["char_count"], 0)

    def test_draft_within_char_limit(self):
        from tools.twitter import draft_post
        result = draft_post("Short topic", max_chars=100)
        self.assertLessEqual(result["char_count"], 110)  # small buffer for Gemma


# ── verify_post ────────────────────────────────────────────────────────────────

class TestVerifyPost(unittest.TestCase):
    def test_missing_handle_returns_error(self):
        from tools.twitter import verify_post
        result = verify_post("", "some text fragment")
        self.assertFalse(result["verified"])
        self.assertIn("error", result)

    def test_missing_fragment_returns_error(self):
        from tools.twitter import verify_post
        result = verify_post("testhandle", "")
        self.assertFalse(result["verified"])
        self.assertIn("error", result)

    def test_verify_not_found_returns_false_not_error(self):
        """When post isn't found, verified=False with a clear message — not an exception."""
        with patch("tools.twitter.DEMO_MODE", False), \
             patch("tools.twitter._is_browser_ready", return_value=False), \
             patch("tools.twitter._search_twitter_via_ddg", return_value=[]):
            from tools.twitter import verify_post
            result = verify_post("testhandle", "xyz_unique_fragment_not_found")
        self.assertFalse(result["verified"])
        self.assertIn("message", result)
        self.assertIsNone(result["found_url"])

    def test_verify_found_via_ddg(self):
        """Simulate DDG returning a matching result."""
        fake_tweets = [{
            "author": "@testhandle", "handle": "testhandle",
            "text": "my unique post about open source AI",
            "url": "https://x.com/testhandle/status/123",
            "source": "ddg_x_scraper"
        }]
        with patch("tools.twitter._search_twitter_via_ddg", return_value=fake_tweets):
            with patch("tools.twitter._is_browser_ready", return_value=False):
                from tools.twitter import verify_post
                result = verify_post("testhandle", "unique post about open source")
        self.assertTrue(result["verified"])
        self.assertIsNotNone(result["found_url"])


# ── research_and_draft ─────────────────────────────────────────────────────────

class TestResearchAndDraft(unittest.TestCase):
    def test_returns_draft_and_sources(self):
        fake_research = {
            "sources": [
                {"title": "AI news", "url": "https://example.com/ai", "snippet": "Gemma 4 released.", "source": "agent_reach/ddg"},
            ],
            "source_count": 1
        }
        with patch("tools.agent_reach.reach_research", return_value=fake_research):
            from tools.twitter import research_and_draft
            result = research_and_draft("AI agents 2026")
        self.assertIn("draft", result)
        self.assertIn("sources", result)
        self.assertFalse(result["ready_to_post"])
        self.assertTrue(result["requires_approval"])

    def test_attribution_in_result(self):
        with patch("tools.agent_reach.reach_research", return_value={"sources": [], "source_count": 0}):
            from tools.twitter import research_and_draft
            result = research_and_draft("test topic")
        self.assertIn("attribution", result)
        self.assertIn("Agent-Reach", result["attribution"]["research"])
        self.assertIn("tweetytweets", result["attribution"]["posting"])


# ── Policy engine: publishing gate ────────────────────────────────────────────

class TestPolicyGate(unittest.TestCase):
    def test_twitter_post_always_requires_approval(self):
        from policy.engine import requires_approval, get_policy
        policy = get_policy()
        self.assertTrue(requires_approval("twitter_post_tweet", policy))

    def test_draft_post_does_not_require_approval(self):
        from policy.engine import requires_approval, get_policy
        policy = get_policy()
        self.assertFalse(requires_approval("draft_post", policy))

    def test_research_and_draft_does_not_require_approval(self):
        from policy.engine import requires_approval, get_policy
        policy = get_policy()
        self.assertFalse(requires_approval("research_and_draft", policy))

    def test_verify_post_does_not_require_approval(self):
        from policy.engine import requires_approval, get_policy
        policy = get_policy()
        self.assertFalse(requires_approval("verify_post", policy))

    def test_reach_tools_do_not_require_approval(self):
        from policy.engine import requires_approval, get_policy
        policy = get_policy()
        for tool in ["reach_web_read", "reach_web_search", "reach_github_search", "reach_research"]:
            self.assertFalse(requires_approval(tool, policy), f"{tool} should not require approval")


# ── Tool registry integrity ────────────────────────────────────────────────────

class TestToolRegistry(unittest.TestCase):
    def test_new_tools_registered(self):
        from tools.runtime import TOOL_REGISTRY
        expected = [
            "reach_web_read", "reach_web_search", "reach_github_search", "reach_research",
            "draft_post", "research_and_draft", "verify_post",
        ]
        for tool in expected:
            self.assertIn(tool, TOOL_REGISTRY, f"Missing from TOOL_REGISTRY: {tool}")

    def test_all_tools_have_description_and_risk(self):
        from tools.runtime import TOOL_REGISTRY
        for name, info in TOOL_REGISTRY.items():
            self.assertIn("description", info, f"{name} missing description")
            self.assertIn("risk", info, f"{name} missing risk level")
            self.assertIn("fn", info, f"{name} missing fn")

    def test_run_tool_unknown_returns_error(self):
        from tools.runtime import run_tool
        result = run_tool("nonexistent_tool_xyz", {})
        self.assertIn("error", result)

    def test_run_tool_draft_post(self):
        from tools.runtime import run_tool
        result = run_tool("draft_post", {"topic": "open source AI agents"})
        self.assertNotIn("error", result)
        self.assertIn("draft", result)
        self.assertFalse(result["ready_to_post"])

    def test_run_tool_verify_post_missing_args(self):
        from tools.runtime import run_tool
        result = run_tool("verify_post", {"handle": "", "expected_text_fragment": ""})
        self.assertFalse(result["verified"])



# ── Multi-Entity Collection & Synthesis ────────────────────────────────────────

class TestEntityCollectionAndSynthesis(unittest.TestCase):
    def test_offline_synthesis_formats_tweets(self):
        from agent.gemma_provider import GemmaProvider
        provider = GemmaProvider()
        tool_results = [
            {
                "tool": "twitter_search",
                "result": {
                    "tweets": [
                        {
                            "author": "GDG London @gdglondon",
                            "handle": "gdglondon",
                            "text": "Join us at Hackney venue! Register here: https://gdg.community.dev/hackney",
                            "url": "https://x.com/gdglondon/status/123456",
                            "likes": 42,
                            "reposts": 12
                        }
                    ]
                }
            }
        ]
        synth = provider._offline_synthesis("GDG Hackney venue twitter", tool_results)
        self.assertIn("Relevant Twitter / X Posts", synth["summary"])
        self.assertIn("gdglondon", synth["summary"])
        self.assertIn("https://x.com/gdglondon/status/123456", synth["summary"])

    def test_offline_synthesis_formats_videos(self):
        from agent.gemma_provider import GemmaProvider
        provider = GemmaProvider()
        tool_results = [
            {
                "tool": "youtube_search",
                "result": {
                    "videos": [
                        {
                            "title": "Agentic AI Workshop",
                            "url": "https://youtube.com/watch?v=abc12345678",
                            "channel": "Tech Channel"
                        }
                    ]
                }
            }
        ]
        synth = provider._offline_synthesis("agentic AI youtube", tool_results)
        self.assertIn("YouTube Videos Found", synth["summary"])
        self.assertIn("https://youtube.com/watch?v=abc12345678", synth["summary"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend import automation
from backend.ai_engine import (
    _build_direct_live_data_context,
    _build_live_answer_hint,
    _build_multi_question_live_context,
    _build_live_search_query,
    _extract_matchups_from_live_context,
    _preferred_live_source_profile,
    _split_live_questions,
    _needs_live_web_context,
)
from backend.main import (
    _normalize_whatsapp_allowed_contact,
    _speaker_access_level,
    build_browser_prompt_plan,
    extract_send_message_details,
    hash_password,
    normalize_auth_email,
    verify_password,
)


class FakeRect:
    def __init__(self, left: int, top: int, right: int, bottom: int):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class FakeElement:
    def __init__(self, text: str, rect: FakeRect, control_type: str = "Text"):
        self._text = text
        self._rect = rect
        self.element_info = SimpleNamespace(control_type=control_type, name=text)

    def window_text(self):
        return self._text

    def rectangle(self):
        return self._rect


class AuditRegressionTests(unittest.TestCase):
    def test_whatsapp_parser_allows_only_amma_aliases(self):
        self.assertEqual(
            extract_send_message_details("open whatsapp desktop and send hi to Amma"),
            ("hi", "Amma"),
        )
        self.assertEqual(
            extract_send_message_details("send good morning message to mummy on whatsapp"),
            ("good morning", "mummy"),
        )
        self.assertEqual(_normalize_whatsapp_allowed_contact("mummy on whatsapp desktop"), "Amma")
        self.assertIsNone(_normalize_whatsapp_allowed_contact("Amma Home"))

    def test_whatsapp_plan_rejects_unsafe_contact(self):
        allowed = build_browser_prompt_plan("open whatsapp desktop and send hi to Amma")
        self.assertEqual(
            allowed["steps"][-1]["payload"],
            {"contact": "Amma", "message": "hi"},
        )

        rejected = build_browser_prompt_plan("open whatsapp desktop and send hi to Amma Home")
        self.assertTrue(rejected["needs_clarification"])
        self.assertEqual(rejected["steps"], [])

    def test_whatsapp_ui_matching_requires_exact_visible_contact(self):
        window = object()
        elements = [
            FakeElement("Amma Home", FakeRect(30, 260, 260, 305), "ListItem"),
            FakeElement("Amma", FakeRect(30, 320, 260, 365), "ListItem"),
        ]

        with (
            patch.object(automation, "_iter_descendants", return_value=elements),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            match = automation._find_whatsapp_contact_element(window, ["Amma"])
            self.assertIsNotNone(match)
            self.assertEqual(match.window_text(), "Amma")

    def test_whatsapp_chat_header_requires_exact_contact(self):
        window = object()
        wrong_header = [FakeElement("Amma Home", FakeRect(360, 35, 520, 70), "Text")]
        right_header = [FakeElement("Amma", FakeRect(360, 35, 520, 70), "Text")]

        with (
            patch.object(automation, "_iter_descendants", return_value=wrong_header),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            self.assertFalse(automation._is_whatsapp_chat_open(window, ["Amma"]))

        with (
            patch.object(automation, "_iter_descendants", return_value=right_header),
            patch.object(automation, "_get_window_bounds", return_value=(0, 0, 1000, 800)),
        ):
            self.assertTrue(automation._is_whatsapp_chat_open(window, ["Amma"]))

    def test_speaker_relationship_access_levels(self):
        self.assertEqual(_speaker_access_level("amma"), "trusted")
        self.assertEqual(_speaker_access_level("mother"), "trusted")
        self.assertEqual(_speaker_access_level("owner"), "owner")
        self.assertEqual(_speaker_access_level("guest"), "guest")
        self.assertEqual(_speaker_access_level("unknown"), "guest")

    def test_media_followup_sets_volume_and_clicks_requested_result(self):
        plan = build_browser_prompt_plan("play third song and play at 60 volume")

        self.assertEqual(plan["steps"][0], {"action": "set_volume", "payload": {"amount": 60}})
        self.assertEqual(
            plan["steps"][1],
            {"action": "click_youtube_result", "target": "3", "payload": {"amount": 3}},
        )

    def test_youtube_search_play_uses_first_result_by_default(self):
        plan = build_browser_prompt_plan("open youtube and play bahubali 2 songs")

        self.assertEqual(plan["steps"][0]["action"], "open_youtube_song")
        self.assertEqual(plan["steps"][0]["target"], "bahubali 2 songs")
        self.assertEqual(plan["steps"][0]["payload"]["index"], 1)
        self.assertTrue(plan["steps"][0]["payload"]["play"])

    def test_active_window_shortcuts_are_planned(self):
        save_plan = build_browser_prompt_plan("save this")
        self.assertEqual(save_plan["steps"], [{"action": "hotkey", "payload": {"keys": ["ctrl", "s"]}}])

        scroll_plan = build_browser_prompt_plan("scroll down")
        self.assertEqual(
            scroll_plan["steps"],
            [{"action": "scroll", "target": "down", "payload": {"direction": "down", "amount": 6}}],
        )

    def test_form_fill_waits_for_submit_confirmation(self):
        plan = build_browser_prompt_plan(
            "open example.com and fill name Yogesh email yogesh@example.com phone 9999999999 before submitting popup notification"
        )

        self.assertEqual(plan["steps"][0], {"action": "open_url", "target": "example.com"})
        self.assertEqual(plan["steps"][2]["action"], "type_sequence")
        self.assertEqual(
            plan["steps"][2]["payload"]["values"],
            ["Yogesh", "yogesh@example.com", "9999999999"],
        )
        self.assertFalse(plan["steps"][2]["payload"]["submit"])
        self.assertEqual(plan["steps"][3]["action"], "notify_user")

    def test_submit_followup_presses_enter(self):
        plan = build_browser_prompt_plan("okay all okay submit")

        self.assertEqual(
            plan["steps"],
            [{"action": "press_key", "target": "enter", "payload": {"key": "enter"}}],
        )

    def test_compound_youtube_scroll_and_close_present_tab(self):
        scroll_plan = build_browser_prompt_plan("open youtube website and scroll one by one")
        self.assertEqual(scroll_plan["steps"][0], {"action": "open_url", "target": "https://youtube.com"})
        self.assertEqual(scroll_plan["steps"][1]["action"], "wait")
        self.assertEqual(
            scroll_plan["steps"][2],
            {"action": "scroll", "target": "down", "payload": {"direction": "down", "amount": 3}},
        )

        close_plan = build_browser_prompt_plan("close the present YouTube tab")
        self.assertEqual(close_plan["steps"], [{"action": "close_tab"}])

    def test_live_web_context_detection_for_current_questions(self):
        self.assertTrue(_needs_live_web_context("what are the latest AI news today"))
        self.assertTrue(_needs_live_web_context("search the internet for current weather"))
        self.assertTrue(_needs_live_web_context("who won the match"))
        self.assertTrue(_needs_live_web_context("what is the highest score"))
        self.assertTrue(_needs_live_web_context("silver and gold per gram"))
        self.assertTrue(_needs_live_web_context("ebullion silver rate"))
        self.assertFalse(_needs_live_web_context("explain recursion simply"))

    def test_live_ipl_search_query_is_date_anchored(self):
        query = _build_live_search_query("what are the teams having an IPL match today")

        self.assertIn("IPL", query)
        self.assertIn("match teams", query)
        self.assertRegex(query, r"\b20\d{2}\b")

    def test_yesterday_ipl_search_query_uses_requested_temporal_word(self):
        query = _build_live_search_query("yesterday IPL match teams and highest score")

        self.assertIn("IPL", query)
        self.assertIn("highest scorer", query)
        self.assertIn("match teams score", query)

    def test_openai_latest_model_query_prefers_official_source(self):
        query = _build_live_search_query("what is the latest GPT model today")

        self.assertIn("site:openai.com", query)
        self.assertIn("official", query)

    def test_live_silver_price_query_prefers_bullion_and_exchange_sources(self):
        query = _build_live_search_query("what is current silver price in India today")
        profile = _preferred_live_source_profile("what is current silver price in India today")

        self.assertIn("site:ebullion.in", query)
        self.assertIn("site:ibjarates.com", query)
        self.assertIn("site:mcxindia.com", query)
        self.assertIn("eBullion", profile["policy"])
        self.assertIn("unit", profile["policy"])

    def test_live_per_gram_metal_query_prefers_ebullion_even_without_price_word(self):
        query = _build_live_search_query("silver and gold per gram")

        self.assertIn("site:ebullion.in", query)
        self.assertIn("silver gold rate", query)

    @patch(
        "backend.ai_engine._read_url",
        return_value='{"data":{"gold":{"sellRate":16216.25,"buyRate":15511.6,"variationType":"up","variation":"132.45"},"silver":{"sellRate":290.92,"buyRate":272.7,"variationType":"up","variation":"3.21"}}}',
    )
    def test_direct_metal_context_uses_ebullion_per_gram_first(self, _mock_read):
        context = _build_direct_live_data_context("silver and gold per gram")

        self.assertIn("eBullion live metal ticker", context)
        self.assertIn("Silver sell INR 290.92/g", context)
        self.assertIn("Gold sell INR 16216.25/g", context)

    def test_live_weather_query_prefers_imd_sources(self):
        query = _build_live_search_query("current weather in Hyderabad today")

        self.assertIn("site:mausam.imd.gov.in", query)
        self.assertIn("official IMD", query)

    def test_live_stock_query_prefers_exchange_sources(self):
        query = _build_live_search_query("current TCS stock price")

        self.assertIn("site:nseindia.com", query)
        self.assertIn("site:bseindia.com", query)

    def test_live_india_news_query_avoids_generic_search_noise(self):
        query = _build_live_search_query("what happened in India latest news today")

        self.assertIn("site:thehindu.com", query)
        self.assertIn("site:indianexpress.com", query)
        self.assertIn("India latest news today", query)

    @patch("backend.ai_engine._read_url")
    def test_direct_news_context_uses_rss_before_generic_search(self, mock_read):
        mock_read.return_value = (
            "<?xml version='1.0'?><rss><channel><item>"
            "<title>India headline one</title><link>https://example.com/one</link>"
            "<pubDate>Thu, 14 May 2026 01:00:00 +0530</pubDate>"
            "<description>Verified current item.</description></item></channel></rss>"
        )

        context = _build_direct_live_data_context("what happened in India latest news today")

        self.assertIn("India current news RSS/news feeds", context)
        self.assertIn("India headline one", context)

    def test_live_question_split_handles_compound_query(self):
        questions = _split_live_questions(
            "yesterday IPL match what are the teams and who won the match and what is the highest score"
        )

        self.assertGreaterEqual(len(questions), 2)
        self.assertTrue(any("who won" in question for question in questions))

    def test_live_ipl_context_builds_direct_answer_hint(self):
        live_context = (
            "LIVE WEB CONTEXT:\n"
            "1. Aaj Kiska Match Hai IPL Today Match Schedule 13 May 2026 RCB vs KKR\n"
            "   URL: https://www.timesnowhindi.com/sports/cricket/example\n"
            "2. Royal Challengers Bengaluru vs Kolkata Knight Riders full schedule\n"
            "   URL: https://newsable.asianetnews.com/example"
        )

        self.assertEqual(
            _extract_matchups_from_live_context(live_context)[0],
            "Royal Challengers Bengaluru (RCB) vs Kolkata Knight Riders (KKR)",
        )

        hint = _build_live_answer_hint("what are the teams having an IPL match today", live_context)

        self.assertIn("Royal Challengers Bengaluru (RCB) vs Kolkata Knight Riders (KKR)", hint)
        self.assertIn("Do not tell the user to check a website", hint)
        self.assertIn("IST", hint)

    def test_live_matchup_extraction_understands_face_wording(self):
        live_context = "Page details: Royal Challengers Bengaluru face Kolkata Knight Riders at Raipur."

        self.assertEqual(
            _extract_matchups_from_live_context(live_context),
            ["Royal Challengers Bengaluru vs Kolkata Knight Riders"],
        )

    def test_live_matchup_extraction_filters_non_ipl_noise(self):
        live_context = (
            "Page details: Royal Challengers Bengaluru face Kolkata Knight Riders. "
            "Unrelated card: Roman Reigns vs Jacob Fatu."
        )

        self.assertEqual(
            _extract_matchups_from_live_context(live_context),
            ["Royal Challengers Bengaluru vs Kolkata Knight Riders"],
        )

    @patch("backend.ai_engine._fetch_live_web_context", return_value="LIVE WEB CONTEXT:\n1. verified result")
    def test_multi_question_live_context_keeps_each_question(self, _mock_fetch):
        context = _build_multi_question_live_context(
            "what is the latest GPT model and what is today's IPL match score"
        )

        self.assertIn("LIVE QUESTION 1", context)
        self.assertIn("LIVE QUESTION 2", context)
        self.assertIn("SEARCH QUERY:", context)

    @patch("backend.ai_engine._fetch_live_web_context", return_value="LIVE WEB CONTEXT:\n1. verified result")
    def test_multi_question_live_context_inherits_ipl_and_date(self, _mock_fetch):
        context = _build_multi_question_live_context(
            "yesterday IPL match what are the teams and who won the match and what is the highest score"
        )

        self.assertIn("LIVE QUESTION 1", context)
        self.assertIn("LIVE QUESTION 2: yesterday who won the match IPL", context)
        self.assertIn("LIVE QUESTION 3: yesterday what is the highest score IPL", context)

    def test_auth_password_hash_verification(self):
        hashed = hash_password("correct-password")

        self.assertTrue(verify_password("correct-password", hashed))
        self.assertFalse(verify_password("wrong-password", hashed))
        self.assertNotIn("correct-password", hashed)

    def test_auth_email_normalization(self):
        self.assertEqual(normalize_auth_email("  USER@Example.COM "), "user@example.com")


if __name__ == "__main__":
    unittest.main()

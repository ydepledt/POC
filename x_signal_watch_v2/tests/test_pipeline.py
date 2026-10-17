import asyncio
import json
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pipeline
from main import demo


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = pipeline.connect_db(Path(self.tmp.name) / "test.db")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    @staticmethod
    def fake_tweet(identifier, text="Lancement décalé", sample=0):
        return {
            "tweet_id": identifier,
            "author": "compte_fictif",
            "text": text,
            "created_at": "2026-10-16T12:00:00+00:00",
            "url": "", "sample": sample,
        }

    def test_deduplicates_tweets_but_keeps_multiple_queries(self):
        tweet = self.fake_tweet("1000")
        count = pipeline.save_tweets(self.conn, [(tweet, "Airbus"), (tweet, "Avion")])
        self.assertEqual(count, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tweet_queries").fetchone()[0], 2)
        self.assertEqual(pipeline.pending_tweets(self.conn)[0]["keywords"], "Airbus, Avion")

    def test_saved_keywords_override_env(self):
        with patch.dict(os.environ, {"KEYWORDS": "Airbus, SpaceX"}):
            self.assertEqual(pipeline.keywords(self.conn), ["Airbus", "SpaceX"])
            pipeline.set_keywords(self.conn, ["Toulouse", "Toulouse", "Espace"])
            self.assertEqual(pipeline.keywords(self.conn), ["Toulouse", "Espace"])

    def test_refuses_hallucinated_source_ids_and_old_event_ids(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1000"), "Espace")])
        tweets = pipeline.pending_tweets(self.conn)
        bad_source = {"events": [{
            "headline": "Alerte", "summary": "Il se passe quelque chose", "importance": 2,
            "tweet_ids": ["99"], "existing_event_id": None,
        }]}
        with self.assertRaisesRegex(ValueError, "inventé une référence"):
            pipeline.parse_events(json.dumps(bad_source), tweets, [])
        bad_event = {"events": [{
            "headline": "Alerte", "summary": "Il se passe quelque chose", "importance": 2,
            "tweet_ids": ["1000"], "existing_event_id": 99,
        }]}
        with self.assertRaisesRegex(ValueError, "ID d'événement"):
            pipeline.parse_events(json.dumps(bad_event), tweets, [])

    def test_fallback_on_429_records_attempts(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1000"), "Espace")])
        tweets = pipeline.pending_tweets(self.conn)
        good = json.dumps({"events": [{
            "headline": "Report possible", "summary": "Un compte rapporte un report.",
            "importance": 3, "tweet_ids": ["1000"], "existing_event_id": None,
        }]})

        class RateLimit(Exception):
            status_code = 429

        calls = []

        def fake_request(provider, model, messages):
            calls.append(model)
            if len(calls) == 1:
                raise RateLimit("Limite atteinte")
            return good, 100, 40

        with patch.dict(os.environ, {"GROQ_API_KEY": "fake", "OPENROUTER_API_KEY": "fake"}):
            with patch.object(pipeline, "call_provider", side_effect=fake_request):
                events, model = pipeline.analyze_with_fallback(self.conn, tweets, [])
        self.assertEqual(model, "openai/gpt-oss-120b")
        self.assertEqual(calls, ["qwen/qwen3.8-27b", "openai/gpt-oss-120b"])
        self.assertEqual(len(events), 1)
        logs = self.conn.execute("SELECT status FROM llm_attempts ORDER BY id").fetchall()
        self.assertEqual([row[0] for row in logs], ["error", "ok"])

    def test_fallback_reaches_openrouter(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1000"), "Espace")])
        tweets = pipeline.pending_tweets(self.conn)
        result = '{"events": []}'

        class RateLimit(Exception):
            status_code = 429

        def fake_request(provider, model, messages):
            if provider == "groq":
                raise RateLimit("quota")
            return result, 99, 10

        with patch.dict(os.environ, {"GROQ_API_KEY": "fake", "OPENROUTER_API_KEY": "fake"}):
            with patch.object(pipeline, "call_provider", side_effect=fake_request):
                events, model = pipeline.analyze_with_fallback(self.conn, tweets, [])
        self.assertEqual(events, [])
        self.assertEqual(model, "deepseek/deepseek-v4-flash-0731:free")

    def test_invalid_api_key_stops_instead_of_hiding_error(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1000"), "Espace")])

        class InvalidKey(Exception):
            status_code = 401

        with patch.dict(os.environ, {"GROQ_API_KEY": "fake"}):
            with patch.object(pipeline, "call_provider", side_effect=InvalidKey("Clé incorrecte")):
                with self.assertRaisesRegex(RuntimeError, "configuration API"):
                    pipeline.analyze_with_fallback(self.conn, pipeline.pending_tweets(self.conn), [])
        self.assertIsNone(self.conn.execute("SELECT analyzed_at FROM tweets").fetchone()[0])

    def test_new_evidence_attaches_to_existing_event(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1000"), "Espace")])
        batch1 = pipeline.pending_tweets(self.conn)
        made = pipeline.apply_analysis(self.conn, batch1, [{
            "headline": "Événement test", "summary": "Test", "importance": 2,
            "category": "Science", "tweet_ids": ["1000"], "existing_event_id": None,
        }], "modèle-test")
        self.assertEqual(made, 1)
        event_id = self.conn.execute("SELECT id FROM events").fetchone()[0]
        pipeline.save_tweets(self.conn, [(self.fake_tweet("1001"), "Espace")])
        made2 = pipeline.apply_analysis(self.conn, pipeline.pending_tweets(self.conn), [{
            "headline": "Événement test", "summary": "Nouvel élément", "importance": 4,
            "category": "Science", "tweet_ids": ["1001"], "existing_event_id": event_id,
        }], "modèle-test")
        self.assertEqual(made2, 0)
        self.assertEqual(self.conn.execute("SELECT importance FROM events").fetchone()[0], 4)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM event_sources").fetchone()[0], 2)

    def test_offline_demo_populates_complete_db(self):
        demo(self.conn)
        stats, last = pipeline.dashboard_stats(self.conn)
        self.assertEqual(stats["tweets"], 9)
        self.assertEqual(stats["events"], 3)
        self.assertEqual(stats["pending"], 0)
        self.assertEqual(last["mode"], "demo-offline")
        self.assertEqual(len(pipeline.dashboard_events(self.conn, sample=1)), 3)
        self.assertTrue(all(not row["url"] for row in pipeline.recent_tweets(self.conn)))

    def test_complete_cycle_with_fake_x_and_fake_llm(self):
        """Collecte -> SQLite -> LLM -> événement -> sources -> tableau de bord."""
        class FakeTweet:
            id = "1999012345678901234"
            user = types.SimpleNamespace(screen_name="source_exemple")
            text = "L'entreprise imaginaire Alpha reporte son essai technique."
            full_text = None
            created_at_datetime = datetime.now(timezone.utc)
            favorite_count = 3
            retweet_count = 1

        class FakeClient:
            def __init__(self, language):
                pass

            async def login(self, **kwargs):
                return {}

            async def search_tweet(self, query, product, count=20):
                self_expected = (query, product)
                if self_expected != ("Alpha", "Latest"):
                    raise AssertionError(self_expected)
                return [FakeTweet()]

        mock_twikit = types.ModuleType("twikit")
        mock_twikit.Client = FakeClient
        response = json.dumps({"events": [{
            "headline": "Essai reporté", "summary": "Une publication évoque un report.",
            "category": "Technologie", "importance": 2,
            "tweet_ids": [FakeTweet.id], "existing_event_id": None,
        }]})
        pipeline.set_keywords(self.conn, ["Alpha"])
        with patch.object(pipeline, "ROOT", Path(self.tmp.name)):
            with patch.dict(os.environ, {"X_USERNAME": "test", "X_PASSWORD": "test", "GROQ_API_KEY": "fake"}):
                with patch.dict(sys.modules, {"twikit": mock_twikit}), patch.object(pipeline, "apply_twikit_compat"):
                    collected = asyncio.run(pipeline.collect_from_x(self.conn))
                with patch.object(pipeline, "call_provider", return_value=(response, 120, 60)):
                    analyzed = pipeline.analyze_pending(self.conn)
        self.assertEqual(collected["inserted"], 1)
        self.assertEqual(analyzed["new_events"], 1)
        events = pipeline.dashboard_events(self.conn, sample=0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source_count"], 1)
        self.assertEqual(pipeline.event_sources(self.conn, events[0]["id"])[0]["url"],
                         "https://x.com/i/web/status/1999012345678901234")

    def test_demo_does_not_touch_pending_real_tweets(self):
        pipeline.save_tweets(self.conn, [(self.fake_tweet("5000"), "Espace")])
        demo(self.conn)
        real = self.conn.execute("SELECT analyzed_at FROM tweets WHERE tweet_id='5000'").fetchone()
        self.assertIsNone(real["analyzed_at"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM events WHERE sample=1").fetchone()[0], 3)

    def test_browser_session_cookies_skip_password_login(self):
        client = types.SimpleNamespace(
            set_cookies=Mock(), load_cookies=Mock(), login=AsyncMock(),
            search_tweet=AsyncMock(return_value=[]),
        )
        fake_module = types.ModuleType("twikit")
        fake_module.Client = Mock(return_value=client)
        pipeline.set_active_topics(self.conn, [])
        pipeline.set_keywords(self.conn, ["Alpha"])
        with patch.object(pipeline, "ROOT", Path(self.tmp.name)), \
                patch.dict(os.environ, {"X_AUTH_TOKEN": "fake-session", "X_CT0": "fake-csrf",
                                        "X_USERNAME": "test", "X_PASSWORD": "test"}), \
                patch.dict(sys.modules, {"twikit": fake_module}), \
                patch.object(pipeline, "apply_twikit_compat"):
            stats = asyncio.run(pipeline.collect_from_x(self.conn))
        self.assertEqual(stats, {"found": 0, "inserted": 0, "errors": []})
        client.set_cookies.assert_called_once_with({"auth_token": "fake-session", "ct0": "fake-csrf"})
        client.login.assert_not_awaited()
        client.load_cookies.assert_not_called()

    def test_twikit_collection_mock_without_network(self):
        class FakeUser:
            screen_name = "journal_demo"

        class FakeTweet:
            id = "9990123456789012345"
            user = FakeUser()
            text = "Texte renvoyé par Twikit simulé"
            full_text = None
            created_at_datetime = datetime.now(timezone.utc)
            favorite_count = 8
            retweet_count = 1

        class FakeClient:
            def __init__(self, language):
                self.calls = []

            async def login(self, **kwargs):
                return {}

            async def search_tweet(self, query, product, count=20):
                self.calls.append((query, product, count))
                return [FakeTweet()]

        fake_module = types.ModuleType("twikit")
        fake_module.Client = FakeClient
        with patch.object(pipeline, "ROOT", Path(self.tmp.name)):
            with patch.dict(os.environ, {"X_USERNAME": "test", "X_PASSWORD": "test", "SEARCH_COUNT": "20"}):
                with patch.dict(sys.modules, {"twikit": fake_module}), patch.object(pipeline, "apply_twikit_compat"):
                    pipeline.set_active_topics(self.conn, [])
                    pipeline.set_keywords(self.conn, ["Avion"])
                    stats = asyncio.run(pipeline.collect_from_x(self.conn))
        self.assertEqual(stats, {"found": 1, "inserted": 1, "errors": []})
        self.assertEqual(self.conn.execute("SELECT author FROM tweets").fetchone()[0], "journal_demo")


if __name__ == "__main__":
    unittest.main()

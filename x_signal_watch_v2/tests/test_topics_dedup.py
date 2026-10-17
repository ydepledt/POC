"""Tests des thèmes, de la déduplication sémantique et de la migration."""
import json
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pipeline


class TopicDedupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "watch.db"
        self.conn = pipeline.connect_db(self.path)

    def tearDown(self):
        self.conn.close()
        self.temp.cleanup()

    @staticmethod
    def tweet(tweet_id, text="Orbitalia reporte son lancement"):
        return {"tweet_id": tweet_id, "text": text, "author": "fake_" + tweet_id,
                "sample": 0, "url": "", "created_at": datetime.now(timezone.utc).isoformat()}

    @staticmethod
    def event(ids, title="Lancement Orbitalia reporté", importance=3):
        return {"headline": title, "summary": "Un report est évoqué sur X.",
                "category": "Science", "importance": importance,
                "tweet_ids": ids, "existing_event_id": None}

    @staticmethod
    def decisions(proposals, event_id=None, confidence=0.95, same_as=None):
        return {"matches": [{
            "index": i, "existing_event_id": event_id if i == 0 else None,
            "same_as_new_index": same_as if i == 1 else None,
            "confidence": confidence, "reason": "Même annonce et même date"}
            for i in range(len(proposals))]}

    def test_default_topics_multiselect_and_persistence(self):
        presets = pipeline.topics(self.conn, active_only=True)
        self.assertEqual({p["id"] for p in presets}, set(pipeline.DEFAULT_TOPICS))
        pipeline.set_active_topics(self.conn, ["gaming", "cyber"])
        self.assertEqual({p["id"] for p in pipeline.topics(self.conn, True)}, {"gaming", "cyber"})
        self.assertEqual(len(pipeline.search_targets(self.conn)), 2)
        self.conn.close()
        self.conn = pipeline.connect_db(self.path)
        self.assertEqual({p["id"] for p in pipeline.topics(self.conn, True)}, {"gaming", "cyber"})
        pipeline.set_active_topics(self.conn, [])
        self.assertEqual(pipeline.search_targets(self.conn), [])

    def test_add_custom_topic_and_filter_by_multiple_themes(self):
        topic = pipeline.add_topic(self.conn, "Aéronautique", "(Airbus OR Safran) lang:fr")
        pipeline.set_active_topics(self.conn, ["ai", "aerospace", topic])
        tx = self.tweet("tx1")
        pipeline.save_tweets(self.conn, [(tx, "Airbus", ["aerospace", topic]),
                                         (tx, "Technologie", ["ai"])])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tweet_topics").fetchone()[0], 3)
        self.assertEqual(len(pipeline.recent_tweets(self.conn, topic_ids=[topic, "gaming"])), 1)
        self.assertEqual(len(pipeline.recent_tweets(self.conn, topic_ids=["gaming"])), 0)
        pending = pipeline.pending_tweets(self.conn)
        pipeline.apply_analysis(self.conn, pending, [self.event(["tx1"])], "offline")
        self.assertEqual(len(pipeline.dashboard_events(self.conn, topic_ids=["gaming"])), 0)
        self.assertEqual(len(pipeline.dashboard_events(self.conn, topic_ids=[topic, "gaming"])), 1)
        self.assertTrue(pipeline.remove_topic(self.conn, topic))
        self.assertFalse(pipeline.remove_topic(self.conn, "ai"))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0], 1)

    def test_invalid_topics(self):
        with self.assertRaises(ValueError):
            pipeline.set_active_topics(self.conn, ["invalid"])
        with self.assertRaises(ValueError):
            pipeline.set_active_topics(self.conn, [x["id"] for x in pipeline.topics(self.conn)][:9])
        with self.assertRaises(ValueError):
            pipeline.add_topic(self.conn, "Z", "X")
        pipeline.add_topic(self.conn, "Sous-traitance", "(sous-traitance) lang:fr")
        with self.assertRaises(ValueError):
            pipeline.add_topic(self.conn, "sous-traitance", "other")

    def test_dedup_model_merges_event_between_cycles_preserving_sources(self):
        pipeline.save_tweets(self.conn, [(self.tweet("a"), "Airbus", ["aerospace"])])
        extraction_a = json.dumps({"events": [self.event(["a"])]})
        with patch.dict(os.environ, {"GROQ_API_KEY": "fake", "OPENROUTER_API_KEY": ""}):
            with patch.object(pipeline, "call_provider", return_value=(extraction_a, 200, 90)) as mocked:
                first = pipeline.analyze_pending(self.conn)
                self.assertEqual(mocked.call_count, 1)  # aucune comparaison nécessaire
        self.assertEqual(first["new_events"], 1)
        original_id = self.conn.execute("SELECT id FROM events").fetchone()[0]
        pipeline.save_tweets(self.conn, [(self.tweet("b", "Le vol d'Orbitalia décalé de 48h"),
                                          "Espace", ["aerospace"])])
        extraction_b = json.dumps({"events": [self.event(["b"], title="Orbitalia décale son tir")]})
        merge = json.dumps(self.decisions([self.event(["b"])], event_id=original_id))
        calls = []
        def simulated_llm(provider, model, messages):
            calls.append(messages[0]["content"])
            return (merge if "arbitre" in messages[0]["content"] else extraction_b), 110, 60
        with patch.dict(os.environ, {"GROQ_API_KEY": "fake", "OPENROUTER_API_KEY": ""}):
            with patch.object(pipeline, "call_provider", side_effect=simulated_llm):
                second = pipeline.analyze_pending(self.conn)
        self.assertEqual(second["new_events"], 0)
        self.assertEqual(second["merged_events"], 1)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM event_sources").fetchone()[0], 2)
        log = pipeline.dedup_history(self.conn)
        self.assertEqual(log[0]["action"], "merged_existing")
        self.assertEqual(log[0]["confidence"], 0.95)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM llm_attempts WHERE stage='deduplication'").fetchone()[0], 1)

    def test_low_confidence_does_not_merge(self):
        proposals = [self.event(["b"])]
        prev = [{"id": 7}]
        content = json.dumps(self.decisions(proposals, event_id=7, confidence=0.78))
        output = pipeline.parse_dedup(content, proposals, prev)
        self.assertIsNone(output[0]["existing_event_id"])
        self.assertEqual(output[0]["dedup_confidence"], 0.78)

    def test_rejects_wrong_event_ids_forged_indices_and_exclusive_conflicts(self):
        events = [self.event(["a"]), self.event(["b"])]
        invalid = self.decisions(events, event_id=10000)
        with self.assertRaisesRegex(ValueError, "ID de déduplication"):
            pipeline.parse_dedup(json.dumps(invalid), events, [{"id": 7}])
        invalid = self.decisions(events, same_as=1)
        with self.assertRaisesRegex(ValueError, "événement futur"):
            pipeline.parse_dedup(json.dumps(invalid), events, [])
        invalid = self.decisions(events, event_id=7, same_as=0)
        with self.assertRaisesRegex(ValueError, "deux événements"):
            # Set both match values on the same index.
            invalid["matches"][1]["existing_event_id"] = 7
            pipeline.parse_dedup(json.dumps(invalid), events, [{"id": 7}])
        invalid = self.decisions(events)
        invalid["matches"][1]["index"] = 0
        with self.assertRaisesRegex(ValueError, "répété"):
            pipeline.parse_dedup(json.dumps(invalid), events, [])

    def test_intra_batch_llm_merge_creates_single_event(self):
        pipeline.save_tweets(self.conn, [(self.tweet("1"), "SpaceX", ["aerospace"]),
                                         (self.tweet("2"), "NASA", ["aerospace"])])
        batch = pipeline.pending_tweets(self.conn)
        events = [self.event(["1"], "Lancement annulé"), self.event(["2"], "Vol reporté")]
        decisions = pipeline.parse_dedup(json.dumps(self.decisions(events, same_as=0)), events, [])
        annotated = [dict(event, **decision, dedup_model="qwen") for event, decision in zip(events, decisions)]
        created = pipeline.apply_analysis(self.conn, batch, annotated, "qwen")
        self.assertEqual(created, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM event_sources").fetchone()[0], 2)
        self.assertEqual(pipeline.dedup_history(self.conn)[0]["action"], "merged_batch")

    def test_transaction_rolls_back_if_merge_invalid(self):
        pipeline.save_tweets(self.conn, [(self.tweet("1"), "SpaceX")])
        events = [dict(self.event(["1"]), existing_event_id=99999)]
        with self.assertRaisesRegex(ValueError, "introuvable"):
            pipeline.apply_analysis(self.conn, pipeline.pending_tweets(self.conn), events, "test")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.assertIsNone(self.conn.execute("SELECT analyzed_at FROM tweets").fetchone()[0])

    def test_403_groq_falls_back_directly_to_openrouter(self):
        pipeline.save_tweets(self.conn, [(self.tweet("403"), "Alpha")])
        calls = []
        class Denied(Exception):
            status_code = 403
        def fake(provider, model, messages):
            calls.append((provider, model))
            if provider == "groq":
                raise Denied("Access denied")
            return json.dumps({"events": [self.event(["403"])]}), 100, 50
        with patch.dict(os.environ, {"GROQ_API_KEY": "fake", "OPENROUTER_API_KEY": "fake"}):
            with patch.object(pipeline, "call_provider", side_effect=fake):
                result = pipeline.analyze_pending(self.conn)
        self.assertEqual(result["new_events"], 1)
        self.assertEqual(calls[0][0], "groq")
        self.assertEqual(calls[1][0], "openrouter")
        self.assertEqual(len(calls), 2)

    def test_paused_collection_does_not_authenticate_to_x(self):
        pipeline.set_active_topics(self.conn, [])
        pipeline.set_keywords(self.conn, [])
        import asyncio
        self.assertEqual(asyncio.run(pipeline.collect_from_x(self.conn)),
                         {"found": 0, "inserted": 0, "errors": []})

    def test_migrate_previous_database_preserves_events_and_saved_keywords(self):
        self.conn.close()
        self.path.unlink()
        old = sqlite3.connect(self.path)
        old.execute("CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
        old.execute("INSERT INTO settings VALUES ('keywords','Alpha, Toulouse')")
        old.execute("CREATE TABLE events(id INTEGER PRIMARY KEY,headline TEXT,summary TEXT,category TEXT,importance INTEGER,model TEXT,sample INTEGER,created_at TEXT,updated_at TEXT)")
        old.execute("INSERT INTO events VALUES(2,'Ancien événement','Texte','Actualité',2,'model',0,'2026-10-16','2026-10-16')")
        old.commit()
        old.close()
        self.conn = pipeline.connect_db(self.path)
        active = pipeline.topics(self.conn, active_only=True)
        self.assertEqual({row["query"] for row in active}, {"Alpha", "Toulouse"})
        self.assertEqual(self.conn.execute("SELECT headline FROM events").fetchone()[0], "Ancien événement")
        self.assertIn("last_update", [row["name"] for row in self.conn.execute("PRAGMA table_info(events)")])


if __name__ == "__main__":
    unittest.main()

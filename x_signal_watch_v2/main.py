"""Commandes : demo, once, watch, analyze, status."""

import argparse
import asyncio
import json
import os
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

from pipeline import (
    ROOT, analyze_pending, apply_analysis, collect_from_x, connect_db,
    dashboard_stats, now_utc, pending_tweets,
    save_run, save_tweets, topics, search_targets,
)


def once(conn):
    started = now_utc()
    stats = {"started_at": started}
    errors = []
    print("[Cycle] Collecte X…")
    try:
        stats.update(asyncio.run(collect_from_x(conn)))
        errors += stats.pop("errors", [])
    except Exception as exc:
        errors.append(f"Collecte: {type(exc).__name__}: {exc}")
    print("[Cycle] Analyse des tweets en attente…")
    try:
        stats.update(analyze_pending(conn))
    except Exception as exc:
        errors.append(f"Analyse: {type(exc).__name__}: {exc}")
    status = "partial" if errors else "ok"
    save_run(conn, "live", stats, status, " | ".join(errors))
    print(f"[Cycle] {json.dumps(stats, ensure_ascii=False)}")
    if errors:
        for error in errors:
            print(f"[Attention] {error}")
    return 1 if errors else 0


def demo(conn, with_llm=False):
    """Tweets et événements entièrement fictifs. Jamais de connexion X."""
    data = json.loads((ROOT / "demo_data.json").read_text(encoding="utf-8"))
    with conn:
        conn.execute("DELETE FROM events WHERE sample=1")
        conn.execute("DELETE FROM tweets WHERE sample=1")
    topic_map = {"Espace": "aerospace", "Technologie": "ai", "Transport": "transport"}
    # Les dates de la démo restent récentes quel que soit le jour où elle est lancée.
    base = datetime.fromisoformat(data["tweets"][0]["created_at"])
    offset = datetime.now(timezone.utc) - timedelta(minutes=85) - base
    for tw in data["tweets"]:
        tw["created_at"] = (datetime.fromisoformat(tw["created_at"]) + offset).isoformat(timespec="seconds")
    inserted = save_tweets(conn, [
        (tw, tw["query"], [topic_map[tw["query"]]]) for tw in data["tweets"]
    ])
    if with_llm:
        print("[Démo] Tweets fictifs, analyse par les vraies API Groq/OpenRouter…")
        result = analyze_pending(conn, sample=1)
    else:
        tw = pending_tweets(conn, limit=100, sample=1)
        events = data["events"]
        new_events = apply_analysis(conn, tw, events, "Démo locale sans LLM")
        result = {"analyzed": len(tw), "new_events": new_events,
                  "merged_events": 0, "model": "Démo locale"}
    save_run(conn, "demo-llm" if with_llm else "demo-offline", {
        "found": len(data["tweets"]), "inserted": inserted, **result,
    })
    print(f"[Démo] {inserted} tweets fictifs ; {result['new_events']} événements.")
    print("[Démo] Lancer : streamlit run dashboard.py")


def main():
    parser = argparse.ArgumentParser(description="X Signal Watch")
    sub = parser.add_subparsers(dest="command", required=True)
    p_demo = sub.add_parser("demo", help="Démonstration sans identifiants X")
    p_demo.add_argument("--llm", action="store_true", help="Appelle les vraies API LLM")
    sub.add_parser("once", help="Un cycle de collecte + analyse")
    sub.add_parser("watch", help="Un cycle toutes les 15 minutes (configurable)")
    sub.add_parser("analyze", help="Analyse les tweets déjà stockés")
    sub.add_parser("status", help="État de la base et des mots-clés")
    args = parser.parse_args()
    with closing(connect_db()) as conn:
        if args.command == "demo":
            demo(conn, args.llm)
        elif args.command == "once":
            raise SystemExit(once(conn))
        elif args.command == "analyze":
            print(analyze_pending(conn))
        elif args.command == "status":
            stats, last = dashboard_stats(conn)
            print(f"Thèmes : {[t['label'] for t in topics(conn, active_only=True)]}")
            print(f"Recherches : {search_targets(conn)}")
            print(f"Chiffres : {stats}\nDernier cycle : {last}")
        elif args.command == "watch":
            interval = max(5, int(os.getenv("POLL_MINUTES", "15")))
            print(f"[Veille] Un cycle toutes les {interval} min. Ctrl+C pour arrêter.")
            try:
                while True:
                    once(conn)
                    time.sleep(interval * 60)
            except KeyboardInterrupt:
                print("\n[Veille] Arrêt demandé.")


if __name__ == "__main__":
    main()

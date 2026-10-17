"""Dashboard Streamlit moderne de X Signal Watch (v2)."""

import html
import os
from contextlib import closing
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from pipeline import (
    add_topic, activity_series, connect_db, dashboard_events, dashboard_stats,
    dedup_history, event_sources, keywords, recent_tweets, remove_topic,
    set_active_topics, set_keywords, topic_counts, topics,
)

st.set_page_config(page_title="X Signal Watch · Radar", page_icon="📡", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Space+Grotesk:wght@500;600;700&display=swap');
:root { color-scheme: dark; }
html, body, [class*="css"], [data-testid="stApp"] { font-family: 'DM Sans',sans-serif; }
[data-testid="stAppViewContainer"] {background: radial-gradient(ellipse at 65% -25%, #1b3152 0%, #0c1525 38%, #0a111f 74%); color:#e7eefb;}
[data-testid="stHeader"] {background: transparent;}
[data-testid="stSidebar"] {background: #0c1526; border-right: 1px solid #26344d;}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {color:#f1f6ff;}
.block-container {padding-top:2rem; padding-bottom:3rem; max-width:1420px;}
h1,h2,h3 {font-family:'Space Grotesk',sans-serif; letter-spacing:-.045em;}
h1 {font-size:2.15rem !important;} h2 {font-size:1.45rem !important;}
hr {border-color:#26344a;}
[data-testid="stVerticalBlockBorderWrapper"] > div {background:rgba(17,29,49,.86);border-radius:18px;}
[data-testid="stMetric"] {background:#14233b; border-radius:14px; padding:14px;}
[data-testid="stMetricValue"] {font-family:'Space Grotesk',sans-serif;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:12px; border-bottom:1px solid #2e3b53;}
[data-testid="stTabs"] [data-baseweb="tab"] {border-radius:9px 9px 0 0; font-weight:700;}
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {color:#cfdaeb; font-weight:600;}
a {color:#62d7e2 !important;}
.hero {display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:16px;padding:1.65rem 1.9rem 1.7rem;
 background:linear-gradient(105deg,rgba(37,66,107,.84),rgba(15,30,52,.96) 70%);
 border:1px solid #3a5575;border-radius:22px;margin-bottom:22px;box-shadow:0 10px 36px rgba(0,0,0,.12);}
.eyebrow {font-size:11px;letter-spacing:2.6px;color:#7bdfe2;font-weight:800;text-transform:uppercase;margin-bottom:11px;}
.hero-title {font-size:38px;color:#f4f8ff;font-family:'Space Grotesk',sans-serif;font-weight:700;letter-spacing:-1.7px;line-height:1.05;}
.hero-text {font-size:13px;color:#bbcde5;margin-top:12px;max-width:610px;line-height:1.6;}
.hero-status {display:inline-flex;align-items:center;gap:8px;border:1px solid #436780;background:#172d44;
 border-radius:40px;padding:8px 13px;color:#d8e8f5;font-size:12px;font-weight:700;white-space:nowrap;}
.pulse {width:8px;height:8px;border-radius:50%;background:#52dab3;box-shadow:0 0 0 4px #52dab31c;}
.stat-card {padding:19px 21px;border:1px solid #2a405e;border-radius:18px;background:linear-gradient(180deg,#162944,#111f34);min-height:130px;}
.stat-top {color:#91a5c0;text-transform:uppercase;letter-spacing:1.2px;font-weight:800;font-size:10px;}
.stat-value {font-family:'Space Grotesk';font-weight:700;color:#f6f9ff;letter-spacing:-1.6px;font-size:38px;line-height:1.25;margin-top:8px;}
.stat-desc {font-size:11px;color:#95adca;margin-top:4px;}
.section-title {color:#f5f8ff;font-family:'Space Grotesk',sans-serif;font-size:19px;font-weight:700;letter-spacing:-.55px;margin:12px 0 9px;}
.kicker {color:#8ca4c3;font-size:12px;margin:3px 0 18px;}
.event-top {display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:10px;}
.pill {display:inline-block;font-size:10px;padding:5px 9px;font-weight:800;border:1px solid #34506f;background:#1a304a;
 color:#a9dce6;border-radius:99px;line-height:1.25;}
.priority-5,.priority-4 {background:#462b38;border-color:#855060;color:#ffbcbd;}
.priority-3 {background:#463a2d;border-color:#786047;color:#ffdcaa;}
.priority-2,.priority-1 {background:#1b3940;border-color:#355d61;color:#b0ebdc;}
.demo {background:#3b3156;border-color:#665487;color:#dac6ff;}
.event-title {font-family:'Space Grotesk';font-size:22px;letter-spacing:-.65px;color:#ecf3ff;font-weight:700;line-height:1.32;margin:6px 0 11px;}
.event-summary {font-size:13px;color:#d0daea;line-height:1.75;}
.event-update {border-left:2px solid #3fc3c7;padding:8px 12px;background:#112b3f;border-radius:0 8px 8px 0;
 color:#b9d9ea;font-size:12px;margin:12px 0;}
.event-meta {font-size:11px;color:#8da6c4;line-height:1.8;margin-top:13px;}
.topic-pill {display:inline-block;padding:5px 9px;border-radius:8px;background:#27334f;border:1px solid #35496b;
 font-size:11px;font-weight:700;color:#d1ddf5;margin-right:6px;margin-bottom:5px;}
.micro {font-size:11px;color:#92a9c5;}
.sidebar-logo {font-family:'Space Grotesk';font-weight:700;color:#f0f6ff;font-size:20px;letter-spacing:-.8px;}
.sidebar-sub {font-size:11px;letter-spacing:1.9px;color:#6cd8d5;text-transform:uppercase;font-weight:800;}
.empty-state {text-align:center;padding:40px 18px;color:#b2c3d9;border:1px dashed #45607b;border-radius:16px;}
@media(max-width:780px) {.hero{padding:1.2rem}.hero-title{font-size:31px}.event-title{font-size:19px}}
</style>
""", unsafe_allow_html=True)


def h(value):
    return html.escape(str(value or ""))


def pretty_date(value, short=False):
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZoneInfo("Europe/Paris"))
        return dt.strftime("%d/%m %H:%M" if short else "%d/%m/%Y à %H:%M")
    except (ValueError, TypeError):
        return str(value)


def filter_topic_chips(ids, lookup):
    if not ids:
        return ""
    return " ".join(
        '<span class="topic-pill">' + h(lookup[t]["emoji"] + " " + lookup[t]["label"]) + '</span>'
        for t in ids.split(",") if t in lookup
    )


def stat_card(title, value, subtitle):
    st.markdown(f'''<div class="stat-card"><div class="stat-top">{h(title)}</div>
        <div class="stat-value">{h(value)}</div><div class="stat-desc">{h(subtitle)}</div></div>''',
        unsafe_allow_html=True)


def render_event(event, conn, topic_lookup, decision=None, condensed=False):
    with st.container(border=True):
        badges = (
            f'<span class="pill priority-{event["importance"]}">PRIORITÉ {event["importance"]}/5</span>'
            f'<span class="pill">{h(event["category"])}</span>'
            f'<span class="pill {"demo" if event["sample"] else ""}">'
            f'{"DÉMO FICTIVE" if event["sample"] else "SIGNAL X NON VÉRIFIÉ"}</span>'
        )
        st.markdown(f'''<div class="event-top">{badges}</div>
            <div class="event-title">{h(event["headline"])}</div>
            <div class="event-summary">{h(event["summary"])}</div>''', unsafe_allow_html=True)
        if event.get("last_update") and event["last_update"] != event["summary"]:
            st.markdown(f'<div class="event-update"><b>Dernier signal · </b>{h(event["last_update"])}</div>',
                        unsafe_allow_html=True)
        chips = filter_topic_chips(event.get("topic_ids"), topic_lookup)
        if chips:
            st.markdown(chips, unsafe_allow_html=True)
        st.markdown(
            f'<div class="event-meta">◷ {h(pretty_date(event["updated_at"], short=True))}'
            f' &nbsp;·&nbsp; ⧉ {event["source_count"]} sources'
            f' &nbsp;·&nbsp; ◉ {event["author_count"]} auteurs distincts'
            f' &nbsp;·&nbsp; IA : {h(event["model"].split("/")[-1])}</div>',
            unsafe_allow_html=True,
        )
        if decision and decision["action"].startswith("merged"):
            confidence = f"{decision['confidence']:.0%}" if decision["confidence"] is not None else "non renseignée"
            st.caption(f"🧠 Rapprochement IA (confiance {confidence}) : {decision['reason']}")
        if not condensed:
            with st.expander(f"↗ Voir les {event['source_count']} publications sources"):
                for tw in event_sources(conn, event["id"]):
                    st.markdown(f"**@{h(tw['author'])}** · {pretty_date(tw['created_at'])}")
                    st.write(tw["text"])
                    if tw["url"] and str(tw["url"]).startswith("https://x.com/"):
                        st.link_button("Voir la publication ↗", tw["url"], use_container_width=False)
                    st.divider()


with closing(connect_db()) as connection:
    current_topics = topics(connection)
    current_keywords = keywords(connection)
    latest_stats, latest_run = dashboard_stats(connection)

topic_lookup = {topic["id"]: topic for topic in current_topics}
active_ids = [topic["id"] for topic in current_topics if topic["enabled"]]

with st.sidebar:
    st.markdown('<div class="sidebar-sub">PERSONAL INTELLIGENCE</div>'
                '<div class="sidebar-logo">📡 X SIGNAL WATCH</div>', unsafe_allow_html=True)
    st.caption("Radar d'actualités · v2.0")
    st.divider()
    st.subheader("Thèmes surveillés")
    st.caption("Plusieurs thèmes possibles. La sélection est enregistrée pour le collecteur.")
    with st.form("themes_form"):
        chosen_ids = st.multiselect(
            "Sélection active", [t["id"] for t in current_topics], default=active_ids,
            format_func=lambda topic_id: topic_lookup[topic_id]["emoji"] + " " + topic_lookup[topic_id]["label"],
            help="8 thèmes maximum ; un thème peut contenir plusieurs termes OR.",
        )
        save = st.form_submit_button("Enregistrer ma veille", use_container_width=True, type="primary")
    if save:
        try:
            with closing(connect_db()) as conn:
                set_active_topics(conn, chosen_ids)
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    with st.expander("➕ Créer un thème personnalisé"):
        with st.form("add_theme"):
            new_label = st.text_input("Nom du thème", placeholder="Ex : Industrie aéronautique")
            new_query = st.text_input("Requête X", placeholder="(Airbus OR Safran) lang:fr")
            submitted = st.form_submit_button("Ajouter et activer", use_container_width=True)
        if submitted:
            try:
                with closing(connect_db()) as conn:
                    chosen = [x["id"] for x in topics(conn, active_only=True)]
                    if len(chosen) >= 8:
                        raise ValueError("Désactive d'abord un thème : limite de 8 actifs.")
                    new_id = add_topic(conn, new_label, new_query)
                    set_active_topics(conn, chosen + [new_id])
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    customs = [topic for topic in current_topics if not topic["built_in"]]
    if customs:
        with st.expander("Gérer les thèmes ajoutés"):
            remove_id = st.selectbox("Thème à supprimer", [t["id"] for t in customs],
                                     format_func=lambda i: topic_lookup[i]["label"])
            if st.button("Supprimer ce thème", use_container_width=True):
                with closing(connect_db()) as conn:
                    remove_topic(conn, remove_id)
                st.rerun()
    with st.expander("Recherches brutes (avancé)"):
        st.caption("Compatibilité v1. Préfère des thèmes personnalisés pour filtrer les actualités.")
        raw_queries = st.text_area("Une requête par ligne", value="\n".join(current_keywords), height=95)
        if st.button("Enregistrer les requêtes", use_container_width=True):
            try:
                with closing(connect_db()) as conn:
                    set_keywords(conn, raw_queries.splitlines())
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    st.divider()
    st.caption("**État des intégrations**")
    st.markdown("🟢 Base SQLite locale")
    st.markdown(("🟢" if os.getenv("GROQ_API_KEY") else "⚪") + " Groq")
    st.markdown(("🟢" if os.getenv("OPENROUTER_API_KEY") else "⚪") + " OpenRouter")
    from pipeline import ROOT
    x_ready = (bool(os.getenv("X_AUTH_TOKEN") and os.getenv("X_CT0"))
               or bool(os.getenv("X_USERNAME") and os.getenv("X_PASSWORD"))
               or (ROOT / "data" / "x_cookies.json").exists())
    st.markdown(("🟢" if x_ready else "⚪") + " Compte X configuré")
    st.caption("Les voyants indiquent la configuration, **pas** la disponibilité des API.")
    st.caption("Collecte : `python main.py watch` dans un deuxième terminal. UI actualisée toutes les 60 s.")

last_label = pretty_date(latest_run["finished_at"], short=True) if latest_run else "Aucun cycle"
st.markdown(f'''<div class="hero"><div><div class="eyebrow">INTELLIGENCE · SOCIAL SIGNALS</div>
    <div class="hero-title">L'actualité, sans le bruit.</div>
    <div class="hero-text">Les événements émergents repérés dans tes thèmes.
    Regroupement sémantique par IA, synthèses sourcées et historique des rapprochements.
    Les publications X ne sont pas des confirmations indépendantes.</div></div>
    <div class="hero-status"><span class="pulse"></span> Dernier cycle · {h(last_label)}</div></div>''',
            unsafe_allow_html=True)

if not active_ids and not current_keywords:
    st.warning("Aucun thème actif : la collecte est en pause. Active au moins un thème dans la barre latérale.")

f1, f2, f3, f4 = st.columns([1, 1, 1.35, 1.6], gap="small")
with f1:
    mode = st.selectbox("Données", ["Toutes", "Réelles", "Démo"], index=0)
with f2:
    period = st.selectbox("Période", ["24 h", "7 jours", "30 jours"], index=1)
with f3:
    selected_filters = st.multiselect("Filtrer par thèmes", options=[t["id"] for t in current_topics],
                                      format_func=lambda t: topic_lookup[t]["label"],
                                      placeholder="Tous les thèmes")
with f4:
    text_filter = st.text_input("Rechercher un signal", placeholder="Entreprise, événement, expression...")

min_importance = st.slider("Importance minimale", 1, 5, 1,
                           help="1 : tous les signaux · 5 : uniquement les plus importants")
sample_filter = {"Toutes": None, "Réelles": 0, "Démo": 1}[mode]
age_hours = {"24 h": 24, "7 jours": 168, "30 jours": 720}[period]


@st.fragment(run_every="60s")
def radar_panel():
    with closing(connect_db()) as conn:
        stats, last = dashboard_stats(conn)
        events = dashboard_events(conn, sample_filter, age_hours, topic_ids=selected_filters,
                                  min_importance=min_importance, search_text=text_filter)
        tweets = recent_tweets(conn, 250, topic_ids=selected_filters, sample=sample_filter,
                               search_text=text_filter, age_hours=age_hours)
        history = dedup_history(conn, limit=500, sample=sample_filter)
        latest_decisions = {}
        for decision in history:
            latest_decisions.setdefault(decision["event_id"], decision)
        merged = sum(max(0, row["source_count"] - 1) for row in events)
        metrics = st.columns(4, gap="small")
        with metrics[0]:
            stat_card("SIGNaux détectés", len(events), "Événements pour les filtres actifs")
        with metrics[1]:
            stat_card("PUBLICATIONS", len(tweets), "Max. 250 dernières correspondances")
        with metrics[2]:
            stat_card("SOURCES REGROUPÉES", merged, "Publications supplémentaires par événement")
        with metrics[3]:
            stat_card("EN ATTENTE D'IA", stats["pending"], "Toutes catégories et périodes")
        if last:
            text = (f"Dernier traitement : {pretty_date(last['finished_at'])} · "
                    f"{last['mode']} · +{last['inserted']} nouveaux tweets · "
                    f"+{last['new_events']} événements")
            if last["status"] == "ok":
                st.caption("✓ " + text)
            else:
                st.warning(text + " · " + str(last["details"] or "Cycle incomplet"))

        overview, news_tab, tweet_tab, audit = st.tabs([
            "◈ Vue d'ensemble", "▤ Actualités", "𝕏 Publications", "⌘ Déduplication & API",
        ])
        with overview:
            left, right = st.columns([1.65, 1], gap="large")
            with left:
                st.markdown('<div class="section-title">Activité du radar</div>', unsafe_allow_html=True)
                st.markdown('<div class="kicker">Tweets ingérés par jour (UTC) · filtres source / thèmes</div>',
                            unsafe_allow_html=True)
                series = activity_series(conn, sample_filter, days=max(1, age_hours // 24),
                                         topic_ids=selected_filters)
                if series:
                    st.area_chart(series, x="jour", y="tweets", height=230)
                else:
                    st.markdown('<div class="empty-state">Aucune activité pour cette sélection.</div>',
                                unsafe_allow_html=True)
            with right:
                st.markdown('<div class="section-title">Thèmes les plus actifs</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="kicker">Répartition · {h(period)}</div>',
                            unsafe_allow_html=True)
                volumes = topic_counts(conn, sample_filter, days=max(1, age_hours // 24))
                if selected_filters:
                    volumes = [item for item in volumes if item["id"] in selected_filters]
                displayed = [item for item in volumes if item["tweets"] > 0][:7]
                if displayed:
                    st.bar_chart([{"Thème": row["emoji"] + " " + row["label"], "Tweets": row["tweets"]}
                                  for row in displayed], x="Thème", y="Tweets",
                                 height=230, horizontal=True)
                else:
                    st.markdown('<div class="empty-state">Les prochains tweets apparaîtront ici.</div>',
                                unsafe_allow_html=True)
            st.markdown('<div class="section-title">À la une sur ton radar</div>', unsafe_allow_html=True)
            st.markdown('<div class="kicker">Classement indicatif par importance, jamais une vérification des faits.</div>',
                        unsafe_allow_html=True)
            if not events:
                st.info("Pas encore d'événement dans ces filtres. Lance la démo : `python main.py demo`.")
            else:
                for event in events[:4]:
                    render_event(event, conn, topic_lookup, latest_decisions.get(event["id"]))

        with news_tab:
            st.markdown('<div class="section-title">Événements dédupliqués</div>', unsafe_allow_html=True)
            st.caption("Chaque carte est un événement distinct selon l'IA ; les tweets similaires restent consultables sous la carte.")
            if not events:
                st.info("Aucun événement ne correspond aux filtres.")
            for event in events:
                render_event(event, conn, topic_lookup, latest_decisions.get(event["id"]))

        with tweet_tab:
            st.markdown('<div class="section-title">Flux des publications</div>', unsafe_allow_html=True)
            st.caption("Tweets bruts conservés pour la traçabilité. La déduplication s'applique aux cartes d'actualité, pas à la suppression des sources.")
            if not tweets:
                st.info("Aucun tweet dans ce filtre.")
            for tw in tweets:
                with st.container(border=True):
                    st.markdown(f"**@{h(tw['author'])}**  ·  {pretty_date(tw['created_at'])}"
                                f"  ·  {'🧪 Fictif' if tw['sample'] else '𝕏 X'}")
                    st.write(tw["text"])
                    chips = filter_topic_chips(tw["topic_ids"], topic_lookup)
                    if chips:
                        st.markdown(chips, unsafe_allow_html=True)
                    st.caption(f"♡ {tw['likes']}  ·  ↻ {tw['reposts']}  ·  "
                               f"{'Analysé' if tw['analyzed_at'] else 'En attente'}")
                    if tw["url"] and str(tw["url"]).startswith("https://x.com/"):
                        st.link_button("Ouvrir sur X ↗", tw["url"])

        with audit:
            st.markdown('<div class="section-title">Pourquoi l’IA a fusionné ces événements</div>',
                        unsafe_allow_html=True)
            st.caption("Une seconde décision LLM compare les événements dans la fenêtre récente. "
                       "Seuil de fusion : 85 %. Le score est une estimation du modèle, "
                       "pas une probabilité calibrée. Les décisions sont historisées.")
            selected = [d for d in history if d["action"].startswith("merged")]
            if selected:
                st.dataframe([
                    {"Date": pretty_date(d["created_at"]), "Événement": d["headline"],
                     "Action": "Fusion inter-cycle" if d["action"] == "merged_existing" else "Fusion intra-cycle",
                     "Confiance": f"{d['confidence']:.0%}" if d["confidence"] is not None else "—",
                     "Motif": d["reason"], "Modèle": d["model"]}
                    for d in selected[:100]
                ], use_container_width=True, hide_index=True)
            else:
                st.info("Aucune fusion sémantique enregistrée. La démo hors ligne propose des groupes préparés.")
            st.markdown('<div class="section-title">Appels API</div>', unsafe_allow_html=True)
            attempts = conn.execute("""SELECT when_at, stage, provider, model, status,
                input_tokens, output_tokens, duration_ms, error
                FROM llm_attempts ORDER BY id DESC LIMIT 60""").fetchall()
            if attempts:
                st.dataframe([dict(row) for row in attempts], use_container_width=True, hide_index=True)
            else:
                st.caption("Aucun appel LLM. La démo hors ligne ne consomme pas de crédits.")
            with st.expander("Historique des cycles de collecte"):
                runs = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 20").fetchall()
                if runs:
                    st.dataframe([dict(row) for row in runs], use_container_width=True, hide_index=True)


radar_panel()

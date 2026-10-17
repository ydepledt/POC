# X Signal Watch 2.0 📡

Un **radar personnel d'actualités sur X** : collecte Twikit par thème, suivi en SQLite, extraction
et **déduplication sémantique d'événements par LLM**, tableau de bord Streamlit en français.

> **Important** : ce logiciel résume des publications X. Une publication, même répétée,
> **ne prouve pas qu'un événement est réel**. La validation journalistique externe n'est pas incluse.
> Twikit utilise des interfaces non officielles de X, susceptibles de changer, limiter ou bloquer
> l'accès. Usage personnel prudent, sans contournement des limitations.

## 1. Démarrage express, Windows

Prérequis : Python **3.11 ou 3.12** et Internet pour installer les paquets.

1. Dézipper l'archive dans un dossier.
2. Double-cliquer sur **`start_demo_windows.bat`**.
3. Attendre l'installation et l'ouverture de Streamlit, normalement sur <http://localhost:8501>.

La démo utilise **9 tweets entièrement fictifs**, générés localement. Elle ne nécessite
aucun compte X et aucune clé API. Les trois cartes initiales sont préparées à l'avance :
**la démo hors ligne n'exécute pas de LLM**.

Après installation, les autres lanceurs sont :

| Fichier | Rôle |
|---|---|
| `start_dashboard_windows.bat` | Ouvrir l'interface sans réinitialiser la démo |
| `start_watch_windows.bat` | Collecter X + lancer l'analyse en continu, dans un **autre terminal** |
| `start_demo_windows.bat` | Installer si nécessaire, recréer seulement les données fictives et ouvrir Streamlit |

La démo ne supprime **jamais** les tweets réels stockés.

### Installation manuelle Windows (PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py demo
.\.venv\Scripts\python.exe -m streamlit run dashboard.py
```

Sur Linux/macOS, remplacer l'installation par `python3 -m venv .venv`, puis
`source .venv/bin/activate` et utiliser `python` / `streamlit` directement.

## 2. Brancher les vraies API

Renseigner `.env` :

```ini
GROQ_API_KEY=ta_cle_groq
OPENROUTER_API_KEY=ta_cle_openrouter
X_AUTH_TOKEN=valeur_du_cookie_auth_token
X_CT0=valeur_du_cookie_ct0
```

Liens : [Groq](https://console.groq.com/keys) et [OpenRouter](https://openrouter.ai/keys).
Ne jamais publier `.env`, les clés ou `data/x_cookies.json` (session X).

Pour récupérer les deux cookies X, ouvrir X dans Chrome et se connecter normalement,
puis **F12 → Application → Cookies → https://x.com**. Copier la valeur du cookie
`auth_token` dans `X_AUTH_TOKEN` et celle de `ct0` dans `X_CT0`, directement dans le
fichier `.env` local. Ne pas les coller dans un chat. Enregistrer le fichier avant
de relancer le collecteur. Ces deux valeurs doivent provenir de la même session ;
les remplacer si X déconnecte cette session.

Les cookies de `.env` sont prioritaires sur `data/x_cookies.json`. La connexion
historique avec `X_USERNAME`, `X_PASSWORD` et `X_EMAIL` reste disponible quand
aucun cookie n'est fourni, mais la nouvelle page de connexion X peut la bloquer
avant même l'envoi des identifiants.

**Démarrer les deux processus séparément** :

```powershell
# Terminal 1 : interface
.\.venv\Scripts\python.exe -m streamlit run dashboard.py

# Terminal 2 : collecte + analyse toutes les 15 min
.\.venv\Scripts\python.exe main.py watch
```

Le cycle `watch` reprend immédiatement les thèmes enregistrés depuis le dashboard.
Une connexion Twikit peut nécessiter une authentification interactive sur X ;
ce prototype ne contourne pas les CAPTCHA ou les restrictions d'accès.

Pour **essayer le vrai LLM sans X**, utiliser `python main.py demo --llm` (appels API réels sur
des tweets fictifs).

## 3. Dashboard 2.0

Interface sombre responsive, quatre onglets :

- **Vue d'ensemble** : indicateurs, graphiques d'activité, répartition des thèmes, actualités prioritaires.
- **Actualités** : carte par événement, priorité, synthèse, sujets liés, nombre d'auteurs et liens sources.
- **Publications** : flux des tweets stockés, conservés avec leurs textes originaux.
- **Déduplication & API** : toutes les fusions sémantiques avec confiance, justification, modèle,
  détail des appels (extraction, déduplication, fallback) et historique de collecte.

Filtres : données réelles / démo, période, un ou plusieurs thèmes, texte libre, importance minimale.
Rafraîchissement toutes les 60 secondes. Le panneau est **consultatif** : il ne remplace pas
le processus `watch`.

### Choix des thèmes

Depuis la barre latérale :

1. Sélectionner **plusieurs thèmes** dans « Thèmes surveillés », puis enregistrer.
2. Pour un thème spécifique, « Créer un thème personnalisé » : nom + requête X.
   Exemple : `Industrie aéronautique` + `(Airbus OR Safran OR Daher) lang:fr`.
3. La prochaine collecte utilisera ces requêtes. **8 thèmes actifs au maximum**, pour éviter
   de solliciter agressivement X.
4. Les filtres de la page servent à afficher les données existantes ; ils **ne modifient pas**
   les recherches actives. Un thème désactivé peut encore apparaître dans l'historique.

Thèmes préconfigurés : IA & technologie, Actualités mondiales, Aérospatial, Économie,
Cybersécurité, Sciences, Climat & énergie, Politique française, Jeux vidéo,
Mobilité & transports, Toulouse & région. Les 3 premiers (IA, Monde, Aérospatial)
sont initialement actifs sur une **nouvelle** base.

Les recherches libres `KEYWORDS` V1 sont toujours compatibles (barre latérale « Recherches
brutes »). Il est préférable de créer un thème, pour que les tweets restent filtrables par sujet.

## 4. Déduplication : comment ça marche

**Niveau 0 · SQLite** : chaque tweet X est stocké une seule fois par ID. Plusieurs requêtes
peuvent associer ce même tweet à plusieurs thèmes. Les textes bruts sont conservés.

**Niveau 1 · Extraction par LLM** : une première analyse regroupe les différentes publications
sur un même événement spécifique au sein d'un lot (jusqu'à 12 tweets).

**Niveau 2 · Déduplication par LLM** : une deuxième analyse compare les événements proposés
aux événements récents déjà en base **et entre eux**. Le modèle décide si deux descriptions
parlent **du même fait**, pas simplement de la même entreprise ou du même sujet.

- La fusion est validée seulement si la confiance déclarée par le modèle est **≥ 0,85**.
- Un jugement incertain devient un **nouvel événement**, jamais une fusion automatique.
- Les rapprochements sont consignés dans `dedup_decisions` (motif, date, confiance, modèle).
- Les sources originales sont conservées et consultables sous leur événement.
- L'IA peut toujours produire des faux positifs/négatifs. Son score de confiance n'est pas
  une probabilité scientifiquement calibrée.
- Comparaison limitée aux **96 dernières heures** (modifiable avec `DEDUP_LOOKBACK_HOURS`).
  Pour de longs événements, augmenter la fenêtre peut alourdir les prompts ; seuls les
  20 candidats jugés les plus pertinents sont effectivement envoyés au modèle.

La déduplication est **atomique en base** : si le LLM renvoie un identifiant inventé ou
une structure invalide, les nouveaux événements ne sont pas écrits et les tweets restent
« en attente » pour un prochain essai.

**Coût** : un lot normal demande généralement une requête LLM pour l'extraction, plus
une pour la déduplication dès qu'il y a quelque chose à comparer. En cas d'erreur ou de
limite de quota, les fallbacks peuvent consommer des requêtes supplémentaires.

## 5. Ordre exact des LLM

1. **Groq** : `qwen/qwen3.8-27b` (prioritaire).
2. **Groq** : `openai/gpt-oss-120b`.
3. **OpenRouter** : `deepseek/deepseek-v4-flash-0731:free`.

Fallback sur quota `429`, timeout, réseau, erreur serveur, absence de modèle (`404`),
réponse JSON invalide. Une erreur **403** de Groq bloque Groq pour cet appel et tente
OpenRouter directement ; les erreurs **400/401** interrompent le cycle pour éviter de cacher
une mauvaise clé ou une requête invalide. Tous les appels et erreurs sont journalisés.
Les API imposent leurs propres limites gratuites, susceptibles de changer.

## 6. Configuration

| Clé `.env` | Défaut | Description |
|---|---|---|
| `SEARCH_COUNT` | 20 | Nombre maximum de tweets renvoyés par requête et cycle (max 20) |
| `POLL_MINUTES` | 15 | Intervalle entre collectes (minimum 5 min) |
| `BATCH_SIZE` | 12 | Tweets transmis par lot au LLM (max 15) |
| `DEDUP_LOOKBACK_HOURS` | 96 | Fenêtre de fusion sémantique, bornée entre 24 et 720 h |
| `KEYWORDS` | vide | Anciennes recherches libres, ajoutées aux thèmes actifs |
| `DB_PATH` | `data/watch.db` | Base SQLite, relative au projet ou chemin absolu |

Commandes complémentaires :

```powershell
python main.py status      # Résumé base + thèmes activés
python main.py once        # Un cycle (collecte + analyse)
python main.py analyze     # Retraite les tweets en attente, sans collecte X
python main.py demo        # Réinitialise uniquement les données démo
python main.py demo --llm  # Démo fictive traitée par les vraies API
python -m unittest discover -s tests -v
```

## 7. Passer du ZIP V1 à la V2

Dézipper **dans un nouveau dossier**. Pour garder les données et les paramètres :

- Copier le fichier `.env` depuis V1 vers V2.
- Copier `data/watch.db` (et `data/watch.db-wal`/`data/watch.db-shm` si présents, processus
  V1 complètement arrêtés) ainsi que `data/x_cookies.json`.
- Lancer V2 : la structure de base est migrée automatiquement à l'ouverture.
  Les anciennes recherches enregistrées sont converties en thèmes personnalisés actifs,
  les anciennes données restent disponibles.
- Toujours conserver une sauvegarde de la V1 avant migration.

**Ne copie jamais les cookies ou clés dans un dépôt public.**

## 8. Limites

Ce n'est pas un streaming temps réel garanti : la collecte repose sur une recherche `Latest`
périodique, une seule page par thème, sans pagination agressive. Des tweets peuvent être
manqués. Le LLM ne vérifie pas les informations avec des médias indépendants ; l'importance
est subjective. Ne pas lancer plusieurs `watch` simultanés sur la même base.

## 9. Erreur Twikit `Couldn't get KEY_BYTE indices`

Twikit 2.3.3 ne reconnaît pas le format des scripts X modifié en mars 2026.
Le projet applique automatiquement le correctif local `twikit_compat.py` avant la
connexion X. Il charge la page applicative `/home` (la page d'accueil publique de X
n'inclut plus le manifeste), accepte les deux formats de manifeste et conserve les
erreurs HTTP de X. Le correctif est limité à la version 2.3.3 ; une version ultérieure de Twikit
utilisera son propre code.

Si X renvoie sa nouvelle page de connexion sans le script, le collecteur affiche
un message demandant `X_AUTH_TOKEN` et `X_CT0` : réutiliser alors une session
navigateur comme décrit à la section 2. Les clés Groq/OpenRouter servent à
l'analyse des publications ; la session X reste nécessaire pour la collecte.

Après une mise à jour des fichiers, arrêter le collecteur existant avec **Ctrl+C**,
puis relancer `python main.py watch` : un processus déjà ouvert ne recharge pas le code.
Sources : [bug amont #408](https://github.com/d60/twikit/issues/408) et
[correctif proposé #410](https://github.com/d60/twikit/pull/410),
[chargement de /home dans XClientTransaction](https://github.com/iSarabjitDhiman/XClientTransaction/blob/master/x_client_transaction/utils.py).

Documentation : [Twikit](https://twikit.readthedocs.io/en/latest/) ·
[Groq, modèles](https://console.groq.com/docs/models) ·
[Groq, quotas](https://console.groq.com/docs/rate-limits) ·
[OpenRouter](https://openrouter.ai/docs/limits) ·
[Streamlit](https://docs.streamlit.io/)

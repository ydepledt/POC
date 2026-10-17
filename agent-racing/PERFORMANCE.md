# Mesures réelles — 11 octobre 2026

Machine : AMD Ryzen 5 5600, 6 cœurs / 12 processeurs logiques, Windows 11. Python 3.14.8, NumPy 2.5.4, Numba 0.68.0. Aucun GPU utilisé. Les temps dépendent de la machine et des autres traitements ; ils ne sont pas des garanties de débit.

## Apprentissage de la démonstration

Source : `data/simulations/demo-1500/{config,metrics,summary}.json`.

| Mesure | Génération 1, aléatoire | Génération 20 |
|---|---:|---:|
| Population | 1 500 | 1 500 |
| Voitures terminant un tour | 2 | 461 |
| Taux de réussite | 0,13 % | 30,73 % |
| Score moyen | 25,43 | 473,20 |
| Meilleur score | 1 340,00 | 1 350,80 |
| Progression maximale | 100 % | 100 % |

Circuit Kidney, difficulté moyenne, seed 42, limite simulée de 48 s par génération. Le maximum initial étant déjà de 100 %, la preuve principale d'amélioration est la distribution des résultats : score moyen et nombre de tours terminés. Le film n'annonce pas une première victoire tardive fictive.

Les 20 générations, leur sélection et leurs sauvegardes ont pris **24,06 s**. Les calculs d'une génération ont pris de **0,47 à 1,48 s**, avec environ **138 000 à 166 000 mises à jour de voitures/s**. Mémoire RSS observée entre générations : au plus **149,43 Mio** pour ce processus. Ce maximum échantillonné n'est pas une mesure continue de toutes les allocations.

Une reproduction indépendante complète a donné **exactement les mêmes 20 générations** pour les scores, distances, compteurs, checkpoints et nombre d'étapes de voiture. Le cerveau sauvegardé a reproduit son score de **1 350,8**. Les tableaux des replays ont été comparés exactement avant l'ajout des heures explicites de collision. Rapport : `data/validation/demo-reproduction.json`.

## Plusieurs seeds et scénarios

Ovale de référence, 200 voitures, 20 générations, même protocole et trois seeds indépendantes :

| Seed | Score moyen initial → final | Tours terminés initial → final |
|---|---:|---:|
| 7 | 40,26 → 480,97 | 2 → 65 |
| 42 | 72,78 → 655,27 | 3 → 91 |
| 123 | 30,04 → 579,88 | 0 → 80 |

Les résultats et configurations sont conservés dans `data/validation/learning.json` et ses sous-dossiers. La comparaison est avec chaque population aléatoire initiale ; ce n'est pas une compétition à budget égal contre une recherche aléatoire répétée, ni une évaluation sur des circuits inconnus.

Autre scénario : piste procédurale, seed 2026, 500 voitures, 12 générations. Réussites **7 → 166**, score moyen **54,58 → 521,60**, entraînement **5,33 s**. Le prototype à 150 voitures sur Kidney passait de **23,75 % à 100 %** de progression en six générations, avec **0 → 78** tours terminés.

## Choix de l'algorithme et profilage

Benchmark d'inférence : mêmes entrées, mêmes poids, mêmes biais, tanh et topologie 8 → 8 → 2, 1 500 réseaux distincts. Les sorties ont été comparées numériquement ; temps médians après préchauffage :

| Exécution | Temps pour 1 500 décisions |
|---|---:|
| NumPy, produit par lot | 0,250 ms |
| Boucles compilées Numba | 0,253 ms |
| NEAT-Python 2.0, `FeedForwardNetwork` | 13,330 ms |
| Mêmes boucles en Python | 31,666 ms |

Sur cette charge homogène, l'exécuteur NEAT mesuré coûte environ 53 fois plus que le calcul par lot. **Ce résultat ne compare pas la qualité d'apprentissage de NEAT à celle de l'algorithme génétique**, et ne mesure pas la recherche de topologie. La topologie fixe facilite ici un état compact et un moteur compilé unique. NumPy et Numba sont presque équivalents pour le réseau seul.

Pour les vrais capteurs du moteur, 130 rayons contre 390 segments prennent **0,128 ms** avec Numba et **64,915 ms** avec la même fonction Python : accélération d'environ **507 fois**, résultats identiques. C'est un bénéfice concret de la compilation des boucles géométriques.

Profil d'un entraînement préchauffé de 3 générations × 1 500 voitures : **3,059 s**, dont **2,563 s (84 %)** dans la simulation et **0,338 s (11 %)** dans l'écriture compressée des NPZ. Le temps de compilation initiale est distinct des mesures préchauffées. Sources : `data/benchmarks/profile.json`, `training.prof`, `benchmark.json` ; scripts de reproduction : `evolution_lab/benchmark.py`, `scripts/profile_training.py`.

Le benchmark bout en bout sur trois générations donne :

| Population | Temps total avec sauvegardes | Médiane calcul/génération | Mises à jour de voitures/s | CPU, équivalent un cœur |
|---|---:|---:|---:|---:|
| 150 | 0,44 s | 0,098 s | 166 730 | 99,4 % |
| 1 500 | 2,99 s | 0,930 s | 167 369 | 99,7 % |

Pour 1 500 agents, pic mémoire du processus rapporté par Windows : **173,88 Mio**. Le CPU est exprimé par rapport à **un cœur**, pas à toute la machine. `steps_per_second` dans les JSON compte les mises à jour individuelles d'agents ; `simulation_steps` compte les pas globaux. Les agents terminés ne consomment plus d'inférence.

## Vidéos

| Export | Résolution / cadence | Durée | Images décodées | Taille |
|---|---|---:|---:|---:|
| Démo 1 500 | 1080 × 1920 / 30 fps | 24 s | 720 | 7 768 963 octets |
| Procédural 500 | 1080 × 1920 / 30 fps | 20 s | 600 | 4 859 993 octets |

H.264, yuv420p, son AAC synthétisé sans musique commerciale. Le MP4 principal a pris **32,392 s** à produire : **27,061 s** de dessin Pillow et **5,331 s** hors dessin. Cette dernière mesure inclut attente du pipe FFmpeg, muxage et décodage de validation ; elle n'isole pas le temps CPU du codec. Un autre export se déroulait pendant une partie de cette mesure.

Les **720 compteurs d'images** du film principal ont été vérifiés contre les replays et leurs empreintes. Générations affichées : **1, 5, 13, 15 et 20**. Sources : `video_metadata.json`, `video_audit.json`. Des images extraites du MP4 final ont été inspectées : `data/simulations/demo-1500/qa-contact.png`.

## Références techniques

La compilation des boucles suit les possibilités documentées par [Numba](https://numba.readthedocs.io/en/stable/user/performance-tips.html). NEAT fait évoluer les topologies ; la comparaison ci-dessus porte uniquement sur son exécuteur pour un réseau donné, conformément à la distinction exposée dans la [documentation NEAT-Python](https://neat-python.readthedocs.io/en/v1.1.0/neat_overview.html). Les chiffres de ce rapport sont ceux de cette machine, pas ceux des documentations.

# État de livraison

Cette version locale est utilisable : elle entraîne réellement les réseaux, conserve leurs résultats et fabrique des MP4 vérifiés. Elle ne prétend pas couvrir toutes les extensions de la vision produit.

## Livré et exécuté

- Environnement isolé installé, FFmpeg portable vérifié, lanceurs Windows et Linux fournis.
- Voitures pilotées par un réseau à chaque pas, 5 à 9 capteurs configurables, physique avec inertie de direction, freinage, traînée et collisions balayées.
- Fitness continue, checkpoints ordonnés, stagnation, sélection, crossover, mutations adaptatives, élitisme et immigration aléatoire.
- 1 500 agents, 20 générations effectivement entraînées ; amélioration de 2 à 461 voitures réussissant un tour.
- Sauvegardes atomiques, meilleur modèle rechargé et reproduction complète identique ; reprise entre processus testée.
- Ovale, Kidney, Technique, Chicane distincts et génération procédurale ; contrôle de largeur/courbure, intersections, continuité et traversabilité physique. 24 cas procéduraux sur trois seeds, quatre difficultés, ouvert/fermé validés.
- Replays sélectifs, montage automatique guidé par événements réels, caméra d'ensemble/suivi/collisions, accélérations/ralentis, voitures terminées distinguées des éliminées.
- MP4 verticaux H.264/AAC, effets sonores originaux, miniatures, titres/descriptions/hashtags et audit de provenance image par image.
- Interface française fonctionnelle : création, suivi, graphiques, journaux, galerie, téléchargements, lecteur de replay, relance et reprise.
- File SQLite, dédoublonnage, retries avec backoff, protection contre plusieurs workers, budgets de ressources, planification volontaire et exports versionnés.
- Après fermeture ou incident, un job avec checkpoint valide reprend automatiquement au redémarrage, avec backoff et au plus trois tentatives. Les arrêts volontaires restent arrêtés. Une sauvegarde invalide, un quota épuisé ou un ancien processus non contrôlable produit une alerte visible ; aucun calcul concurrent n'est lancé aveuglément.
- Un lancement réel effectué **avec le bouton du navigateur** : seed 909, 150 voitures, trois générations, checkpoint et MP4 20 s. La lecture Canvas a également été déclenchée et vérifiée.

## Fichiers directement utilisables

Depuis le dossier `C:\Users\yannd\Documents\agent-racing` :

| Fichier | Contenu |
|---|---|
| `start_app.bat` | Ouvre l'application locale |
| `data/simulations/demo-1500/video.mp4` | Film principal, 24 s, 1080 × 1920 |
| `data/simulations/demo-1500/thumbnail.png` | Miniature principale |
| `data/simulations/demo-1500/best_brain.npz` | Réseau champion sauvegardé |
| `data/simulations/procedural-2026/video.mp4` | Deuxième scénario, 20 s |
| `data/simulations/video-prototype/video.mp4` | Premier prototype réel, 150 voitures |
| `data/validation/pytest.xml` | Résultat machine des tests |
| `data/validation/test-results.txt` | Sortie complète des tests |
| `data/validation/demo-reproduction.json` | Reproduction des 20 générations et du cerveau |
| `PERFORMANCE.md` | Mesures, protocole et limites d'interprétation |

Le serveur est limité à `127.0.0.1`. L'installation n'expose pas le laboratoire sur Internet.

## Validation finale

**59 tests passent** (19,39 s) : moteur/évolution, pistes, checkpoints, mutations, intégrité, reprise déterministe, FFmpeg et audit des images, API, file, verrous, erreurs, sauvegarde → redémarrage → vrai MP4. Deux avertissements de dépréciation de bibliothèques de test restent sans échec. Le journal complet et le XML sont dans `data/validation/`.

Le contrôle navigateur a vérifié création d'une simulation, fin du job, vidéo disponible et lecture du replay. Le serveur a ensuite été redémarré avec la version finale, sans job actif ; les expériences conservées sont visibles dans la galerie et la planification demeure désactivée. Les captures d'images extraites des MP4 ont été inspectées.

## Limites explicites

- **Publication sociale partielle** : seuls préparation de brouillons, états par plateforme, liens officiels et export local sont livrés. Les connecteurs OAuth, gestion de tokens et envois via API ne sont pas implémentés/testés. Il faudra les développer, fournir les applications OAuth et autorisations personnelles, puis valider les permissions avant toute publication. Aucun contenu n'a été publié.
- **Planification locale** : l'application doit rester ouverte et la machine éveillée. Aucun service Windows, démarrage automatique système ou agent cloud n'a été installé. La planification reste désactivée à la livraison.
- **Forme des circuits** : `corners` et `hairpins` sont des indications de forme, sans garantie d'un nombre exact de virages ou d'épingles. Il n'y a pas de paramètre dédié à des lignes droites exactes. Les pistes impossibles sont rejetées ou régénérées.
- **Périmètre du moteur** : un seul scénario de conduite, pas d'obstacles mobiles ni de collision entre voitures. Pas de NEAT d'entraînement ni de GPU ; la comparaison NEAT est un benchmark d'inférence. Pas de garantie de généralisation hors du circuit appris.
- **Rendu** : un style Graphite original est fourni ; le champ réservé `visual_style` n'est pas un catalogue de thèmes. Les replays sont enregistrés à 10 Hz par défaut ; l'export 30 fps utilise les états enregistrés les plus proches aux instants du montage.
- **Rétention** : aucun nettoyage automatique de modèles ou vidéos archivés. Le budget disque bloque les nouveaux jobs au besoin ; les replays intermédiaires sont échantillonnés pendant l'entraînement.
- **Portabilité** : Windows réellement testé. Lanceurs et code Linux/WSL fournis, mais pas d'exécution Linux disponible dans cette session.

Les prérequis externes sont décrits par [YouTube](https://developers.google.com/youtube/v3/docs/videos), [TikTok](https://developers.tiktok.com/docs/en/content-posting-api-get-started?enter_method=left_navigation) et la [collection officielle Meta pour Instagram](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api). Ils ne bloquent jamais le calcul ni les exports locaux.

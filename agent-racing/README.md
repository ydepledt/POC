# Evolution Lab

Une application locale pour entraîner de vraies voitures neuronales, rejouer leurs générations et fabriquer des vidéos verticales. Le calcul fonctionne sur CPU, sans compte externe.

## Utilisation

**Windows : double-cliquez sur `start_app.bat`.** L'environnement isolé est déjà installé sur cette machine. Pour une nouvelle installation, lancez d'abord `install.bat` ; Python 3.11 ou plus récent et une connexion Internet sont nécessaires à l'installation seulement. FFmpeg est fourni par une dépendance portable.

L'interface s'ouvre à **http://127.0.0.1:8765**. Gardez la fenêtre du lanceur ouverte pendant les calculs. Pour fermer, fermez cette fenêtre ; une reprise est possible depuis la dernière génération sauvegardée.

1. **Nouvelle simulation** : choisissez circuit, difficulté, population, générations, seed et budget, puis lancez.
2. **Suivi** : consultez les vrais scores et journaux ; arrêtez proprement si nécessaire.
3. **Galerie** : regardez/téléchargez les vidéos, inspectez les métriques, rejouez les générations conservées, reprenez un entraînement ou régénérez son montage.
4. **Automatisation** : configurez la fréquence, le nombre de vidéos et la destination, puis activez volontairement la planification. Elle est **désactivée par défaut** et fonctionne lorsque l'application reste ouverte. Un seul job s'exécute à la fois.

Linux/WSL : `sh install.sh`, puis `sh start_app.sh`. Les scripts sont fournis ; la validation de cette livraison a été réalisée sous Windows.

## Démonstrations et preuves

- `data/simulations/demo-1500/` : expérience de 1 500 voitures, circuit Kidney, difficulté moyenne, seed 42, 20 générations.
- `data/simulations/video-prototype/video.mp4` : première vidéo réelle, 150 voitures et six générations.
- `data/validation/learning.json` : expériences indépendantes sur trois seeds et comparaison avec leur population initiale aléatoire.
- `data/benchmarks/` : mesures reproductibles du moteur et de l'inférence.
- `PERFORMANCE.md` et `DELIVERY.md` : résultats mesurés, validations et limites de la livraison.

Chaque dossier de simulation contient la configuration, le circuit, les métriques, un checkpoint reprenable, le meilleur cerveau et quelques replays. Après montage, il contient aussi `video.mp4`, `thumbnail.png`, `publication.json` et `video_metadata.json`. Ce dernier relie **chaque image exportée** à sa génération, son instant et ses compteurs réels, avec les empreintes SHA-256 des replays.

Exception : `video-prototype` est la copie de montage de l'entraînement `engine_kidney_150`, conservé séparément avec ses modèles. Ces deux entrées de galerie représentent le même entraînement initial, pas deux preuves indépendantes.

## Ce que les voitures apprennent

Les sept capteurs par défaut mesurent les distances aux bordures. La huitième entrée est la vitesse. Un réseau tanh **8 → 8 → 2** produit direction et accélération/freinage à chaque pas. Aucun contrôleur prédéfini ne pilote les individus évolués. Les poids et biais sont initialement aléatoires, puis sélectionnés, croisés et mutés avec conservation d'une élite.

La physique utilise un modèle de bicyclette avec inertie de direction, accélération, freinage et traînée. Les collisions testent un disque englobant la voiture sur tout son déplacement. Les agents ne se heurtent pas entre eux : chaque cerveau est évalué sur la même piste et dans les mêmes conditions. Les voitures terminées sont distinctes des accidentées.

Le score récompense la progression continue et les portes franchies dans l'ordre, puis un tour terminé et son temps. Les demi-tours ne rapportent pas de nouveau progrès ; l'immobilité est éliminatoire. Un contrôleur géométrique séparé vérifie la traversabilité des pistes ; il n'entre jamais dans les populations neuronales.

Les résultats prouvent une adaptation aux circuits entraînés. Ils ne démontrent pas une capacité à conduire sur n'importe quel circuit inédit. Une population aléatoire peut contenir quelques voitures qui réussissent dès le début ; le montage et les métriques doivent le montrer honnêtement.

## Automatisation et publication

La file SQLite conserve jobs, tentatives, horaires et historique. Elle reprend les tâches interrompues, limite mémoire/stockage/threads et applique des retries avec backoff. Les fichiers archivés ne sont pas supprimés automatiquement. Les replays intermédiaires redondants sont échantillonnés pendant l'entraînement afin de borner le stockage.

Les vidéos sont produites **en brouillon local**. L'interface prépare les exports et indique les prérequis officiels YouTube, TikTok et Instagram. Les connexions OAuth et l'envoi sur les réseaux ne sont pas opérationnels dans cette version et aucun token personnel n'est demandé ou enregistré. L'export manuel fonctionne indépendamment de ces intégrations.

## Organisation et commandes de maintenance

`evolution_lab/core` contient physique, circuits et évolution ; `training.py` gère les sauvegardes ; `rendering` et `video` réalisent le montage ; `ui`, `automation` et `publishing` gèrent l'application locale et les exports.

Ces commandes sont facultatives pour l'utilisateur de l'interface :

```powershell
.\.venv\Scripts\python.exe -m evolution_lab doctor
.\.venv\Scripts\python.exe -m evolution_lab run --config configs/demo.json --run-dir data/simulations/mon-experience
.\.venv\Scripts\python.exe -m evolution_lab train --config configs/demo.json --run-dir data/simulations/mon-experience --resume
.\.venv\Scripts\python.exe -m evolution_lab render --run-dir data/simulations/mon-experience
.\.venv\Scripts\python.exe -m evolution_lab validate data/simulations/mon-experience/video.mp4
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip install -r requirements-benchmark.txt
.\.venv\Scripts\python.exe -m evolution_lab benchmark
```

Une reprise conserve la seed, le circuit, les paramètres physiques et génétiques ; les budgets et la limite de générations peuvent être étendus. Pour changer de tâche ou de seed, créez une nouvelle simulation. `requirements-lock.txt` décrit exactement l'environnement ayant servi aux validations ; `requirements.txt` laisse le gestionnaire choisir les versions compatibles avec la version de Python installée.

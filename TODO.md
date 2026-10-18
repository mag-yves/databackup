# TODO — DataBackup

État courant : **phase d'analyse**. Le projet est initialisé (structure documentaire, suivi
du temps, `install.sh` + référence du CLI Proton Drive) ; **aucun code** n'est encore écrit.
Le périmètre fonctionnel est en cours de rédaction dans `cdc.md` (sections ⬜ et §12).

**Règle** : on code une itération **seulement après** validation de la section correspondante
du CDC. Une itération = un objectif mesurable + un livrable testable. Tout ce qui n'est pas
dans l'itération en cours part au backlog, il n'est pas codé « au passage ».

---

## I0 — Analyse et CDC ⏳ **en cours**

- **Objectif** : figer le périmètre v1 (sources, format des archives, destination, exécution).
- **Livrable** : `cdc.md` sans section ⬜ bloquante pour I1–I4.
- **DoD** : les questions du CDC §12 tranchées ou explicitement reportées en évolution (§13).
- **Avancement** : **lot A** (contenu des archives) tranché le 2026-10-18 — nommage normalisé,
  `ZIP_STORED` pour les formats compressés, aucun filtrage, liens symboliques ignorés.
  Restent les **lots B** (transfert et secret) et **C** (archive et restitution).

## I1 — Socle technique

- **Objectif** : squelette exécutable **sans logique métier**.
- **Livrable** : `start.sh` (venv + lanceur), `pyproject.toml` (ruff/pytest, config projet),
  `requirements.txt` / `requirements-dev.txt`, module principal, commandes
  `scan | archive | transfer | cleanup | all`, logging horodaté dans `logs/` (rotation),
  `--dry-run`.
- **DoD** : `./start.sh scan` démarre et journalise ; `ruff` et `pytest` passent ; tests du
  parseur d'arguments et du logger ; `.gitignore` couvre binaire, venv, logs et secrets.

## I2 — Scan des sources

- **Objectif** : savoir **ce qui serait sauvegardé**, sans rien écrire ni envoyer.
- **Livrable** : étape `scan` : dossiers retenus, exclus, vides, volume estimé, et le nom
  d'archive prévu pour chacun.
- **DoD** : tests sur une arborescence **factice** (exclusions, dossiers vides, liens
  symboliques, fichiers temporaires) ; aucune écriture dans les sources (contrôle après run).

## I3 — Création des archives

- **Objectif** : produire les archives dans le dossier temporaire.
- **Livrable** : étape `archive` selon le format acté (CDC §4) : nommage, préservation de
  l'arborescence interne, dossier temporaire vidé avant chaque exécution.
- **DoD** : tests sur données factices — contenu de l'archive vérifié (fichiers et chemins
  relatifs), cas d'un dossier non vide en profondeur, fichiers volumineux stockés si le
  format le prévoit ; sources intactes après run.

## I4 — Transfert vers Proton Drive

- **Objectif** : envoyer les archives vers `/my-files/databackup`.
- **Livrable** : étape `transfer` : un `upload` par archive, stratégie de conflit actée,
  reprise après `auth login` en cas d'échec, comptage et journalisation des échecs.
- **DoD** : tests avec une **doublure** de `proton-drive` (succès, échec, retry après login,
  binaire absent) ; puis un **transfert réel** de bout en bout avec une petite archive non
  critique.

## I5 — Enchaînement complet, nettoyage et restitution

- **Objectif** : une exécution complète fiable, du scan au nettoyage.
- **Livrable** : commande `all` par défaut (scan → archive → transfer → cleanup), nettoyage
  garanti **même en cas d'échec**, code de sortie fiable (0/1), récapitulatif final affiché
  et journalisé.
- **DoD** : test d'un run complet sur données factices ; aucun résidu dans le dossier
  temporaire après un échec de transfert simulé.

## I6 — Restauration et documentation utilisateur

- **Objectif** : pouvoir relire ses documents depuis Proton Drive.
- **Livrable** : procédure de restauration écrite (`cdc.md` §10 + `README.md`) et **testée**.
- **DoD** : un document restauré est **identique à l'original** (comparaison d'empreinte) ;
  la procédure est rejouable par quelqu'un qui n'a pas écrit le script.

## I7 — Planification *(optionnel, à décider au CDC §8)*

- **Objectif** : exécuter la sauvegarde sans intervention.
- **Livrable** : tâche planifiée (cron ou timer systemd) + documentation dans `README.md`.
- **DoD** : deux exécutions planifiées réussies ; comportement vérifié si une exécution
  précédente tourne encore (verrou).

---

## Backlog (hors v1 — ne pas coder sans décision actée au CDC §13)

- historique daté côté distant (au lieu du miroir de l'état courant) ;
- sauvegarde incrémentale (n'envoyer que ce qui a changé) ;
- notification de fin (mail ou notification bureau) ;
- commande de restauration outillée (`./start.sh restore`) ;
- autres sources : photos, dépôts Git, bases de données ;
- contrôle d'intégrité périodique des archives distantes ;
- interface de suivi (dernières sauvegardes, volumétrie).

---

## Rappels d'exploitation

```bash
devtime status                  # état du chrono
./install.sh                    # binaire proton-drive (non versionné)
./proton-drive auth login       # connexion (navigateur, interactif)
./proton-drive filesystem list /my-files   # vérifier la destination
```

- Le binaire `proton-drive` (~93 Mo) n'est **pas versionné** ; après un clone, lancer
  `./install.sh`.
- La destination `/my-files/databackup` doit exister (à créer au premier run ou à la main :
  `./proton-drive filesystem create-folder /my-files databackup`).

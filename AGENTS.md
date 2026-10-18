# AGENTS.md — DataBackup

Sauvegarde **par dossier** de mes **documents**, puis transfert vers **Proton Drive**.
Script **Python** exécuté en local. Documentation et messages de commit **en français**.

Le cahier des charges est la **source de vérité** : `cdc.md`. Tout écart fonctionnel y est
écrit et validé **avant** d'être codé. Les itérations en cours sont dans `TODO.md`.

## Commandes

```bash
.venv/bin/pip install -r requirements.txt       # dépendances d'exécution
.venv/bin/pip install -r requirements-dev.txt   # pytest + ruff
.venv/bin/python -m pytest                       # suite de tests
.venv/bin/ruff check .                           # lint (config : pyproject.toml)
./install.sh                                     # télécharge le binaire proton-drive
./start.sh [scan|archive|transfer|cleanup|all]   # lancement (défaut : all)
```

`start.sh`, `pyproject.toml` et le code applicatif sont **à créer** (cf. `TODO.md` I1) :
aujourd'hui le projet n'a que sa documentation et son outillage de référence.

## Règles du projet (à respecter)

- **CDC d'abord** : pas de code pour une fonctionnalité non décrite et validée dans `cdc.md`.
- **Les sources sont en lecture seule** : le projet ne modifie, ne déplace et ne supprime
  jamais un document. Seul le dossier temporaire de travail est écrit puis vidé.
- **Aucun secret en clair** : ni mot de passe d'archive, ni identifiant, ni chemin personnel
  dans le code ou un fichier versionné (cf. `cdc.md` §7 et §11).
- **Aucun écrasement côté distant sans décision explicite** : la stratégie de conflit
  Proton Drive est fixée dans `cdc.md` §5.
- **`start.sh` doit rester compatible Piloter** : lanceur unique du projet, contrat détaillé
  au `cdc.md` §8 (sans TTY, codes retour, sortie ligne par ligne, annulable, verrou
  `.databackup.lock`). Ne pas casser ce contrat sans le réécrire d'abord dans le CDC.
- La référence de fonctionnement du CLI Proton Drive est `usage-proton-drive-cli.md`.

## Structure

- `cdc.md` — cahier des charges (source de vérité fonctionnelle).
- `memory.md` — mémoire de projet : état courant et prochaines actions (volatile).
- `TODO.md` — itérations prévues, avec objectif et critère de fin.
- `usage-proton-drive-cli.md` — aide de l'exécutable `proton-drive`.
- `install.sh` — téléchargement du binaire `proton-drive` dans le projet.
- `logs/` — logs horodatés (rotation prévue : les N derniers).
- `time-tracker/` — suivi du temps (`devtime`) : `log.json` est **versionné**.
- `.opencode/commands/` — commandes projet `/time-*`.
- **Non versionné** : `proton-drive` (binaire, ~93 Mo), `.venv/`, `logs/`, secrets de config.

## Pièges à connaître

- **`proton-drive auth login` est interactif** (ouverture du navigateur) : il ne peut pas
  s'exécuter sans l'utilisateur devant l'écran. Le script ne fait ni `login` ni `logout`
  systématique : il tente une reconnexion **seulement après un échec** d'upload.
- **Le binaire `proton-drive` n'est pas versionné** : après un clone, lancer `./install.sh`.
- **Mot de passe d'archive** : `autobackup` le garde encore en dur dans son code (dette
  connue) — **ne pas reproduire** ce choix ici ; le CDC §7 et §11 fixent l'emplacement.
- **Volume des transferts** : Proton a un quota ; vérifier l'espace avant une grosse
  sauvegarde (à trancher au CDC §5).

## Mémoire de projet

- **Rôle** : `memory.md` porte l'**état volatile** (où on en est, décisions actées, dettes,
  prochaines actions) ; les règles stables vivent ici et dans `cdc.md`.
- **Lecture** : au début de chaque session, lire `memory.md` avant de commencer.
- **Mise à jour** : après tout changement significatif, actualiser `memory.md`.
- **Plafond** : ~40 lignes / 2 Ko. En cas de dépassement, compresser — les détails vont dans
  `cdc.md` ou l'historique git, et `memory.md` ne garde qu'une ligne de synthèse.
  Ne pas dupliquer les règles de ce fichier.

## Suivi du temps

- **Rappel de début de session** : au premier message de chaque session, exécute
  `devtime status` et affiche un rappel concis — temps cumulé du jour, dernière session —
  puis rappelle que `/time-start` démarre le chrono.
- **Encadrement** : chaque session de travail commence par `/time-start` et se termine par
  `/time-stop`. Les pauses se gèrent par un stop/start (elles sont donc exclues du temps).
- **Données** : `time-tracker/log.json` (versionné). Ne pas l'éditer à la main sans raison.
- **Commandes projet** : `/time-start`, `/time-stop`, `/time-status`, `/time-report`.

# TODO — DataBackup

État courant : **I1 à I6 livrés et vérifiés en réel** le 2026-10-18 — run complet à froid :
**14:25** pour 22 archives (4,63 Go), 0 échec, `timeout` Piloter de 1 h confirmé ; 77 tests
verts, `ruff` propre ; `README.md` complet. **La v1 est terminée** ; la suite est au backlog.

**Règle** : on code une itération **seulement après** validation de la section correspondante
du CDC. Une itération = un objectif mesurable + un livrable testable. Tout ce qui n'est pas
dans l'itération en cours part au backlog, il n'est pas codé « au passage ».

---

## I0 — Analyse et CDC ✅ **FAIT** (2026-10-18)

- **Objectif** : figer le périmètre v1 (sources, format des archives, destination, exécution).
- **Livrable** : `cdc.md` complet — décisions récapitulées au §12.
- **Résultat** : lots **A** (contenu des archives), **B** (transfert et secret) et **C**
  (échecs, restitution, planification) tranchés ; **restauration reportée hors v1** (§10) et
  **planification définitivement exclue** (§2, §8). Reste une vérification (non bloquante) :
  le premier run réel complet, pour mesurer la durée.

## I1 — Socle technique ✅ **FAIT** (2026-10-18)

- **Objectif** : squelette exécutable **sans logique métier**.
- **Livrable** : `start.sh` (venv + lanceur, **conforme au contrat Piloter du CDC §8** : sans
  TTY, codes retour, sortie ligne à ligne, annulable, verrou `.databackup.lock`),
  `pyproject.toml` (ruff/pytest, config projet), `requirements.txt` / `requirements-dev.txt`,
  module principal, commandes `scan | archive | transfer | cleanup | all`, logging horodaté
  dans `logs/` (rotation), options `--dry-run` et `--limit N`, lecture du mot de passe dans
  `.env` (priorité à `DATABACKUP_ZIP_PASSWORD`).
- **DoD** : `./start.sh scan` démarre et journalise ; un second lancement est **refusé par le
  verrou** (code 5) et `SIGTERM` le libère proprement ; `--dry-run` n'écrit rien et n'envoie
  rien ; `ruff` et `pytest` passent ; tests du parseur d'arguments, du logger, du verrou et de
  la résolution du mot de passe ; `.gitignore` couvre binaire, venv, logs, `.env` et secrets ;
  **aucun secret dans le code ni dans les logs**.
- **Résultat** : `databackup.py` porte l'ossature (arguments, journal + rotation, verrou PID
  repris s'il est obsolète, résolution du secret, arrêt propre SIGTERM/SIGINT, codes retour
  `0`–`5`, `--dry-run` / `--limit`) ; `start.sh` fait `exec` du module (groupe de processus
  préservé). Les étapes `scan` / `archive` / `transfer` sont des **ébauches** (log + code 0) :
  la logique arrive en I2/I3/I4. **26 tests** verts, `ruff` et `ruff format` propres.

## I2 — Scan des sources ✅ **FAIT** (2026-10-18)

- **Objectif** : savoir **ce qui serait sauvegardé**, sans rien écrire ni envoyer.
- **Livrable** : étape `scan` : dossiers retenus, exclus, vides, volume estimé, et le nom
  d'archive prévu pour chacun.
- **DoD** : tests sur une arborescence **factice** (exclusions, dossiers vides, liens
  symboliques, fichiers temporaires) ; aucune écriture dans les sources (contrôle après run).
- **Résultat** : `scan` construit le plan — nommage normalisé (§4), `documents.zip` pour la
  racine, dossiers vides exclus, liens symboliques ignorés + avertis, collisions → **échec du
  scan** ; `--limit N` retient les N premiers dossiers (les fichiers racine restent inclus).
  **21 tests** ajoutés (dont un contrôle d'empreinte : aucune écriture dans `source/`).
  Run réel : **22 archives**, **4,70 Go**, 2 315 fichiers, **1 lien symbolique** interne
  détecté (`Prusa/Modèles/02 en cours/Zetests`, ignoré) — CDC §3 corrigé en conséquence.

## I3 — Création des archives ✅ **FAIT** (2026-10-18)

- **Objectif** : produire les archives dans le dossier temporaire.
- **Livrable** : étape `archive` selon le format acté (CDC §4) : nommage, préservation de
  l'arborescence interne, dossier temporaire vidé avant chaque exécution.
- **DoD** : tests sur données factices — contenu de l'archive vérifié (fichiers et chemins
  relatifs), cas d'un dossier non vide en profondeur, fichiers volumineux stockés si le
  format le prévoit ; sources intactes après run.
- **Résultat** : `archive` vide `backup/` **avant** l'exécution puis écrit les zips **AES-256**
  (vérifié : force 3) — arborescence interne fidèle (chemins relatifs), **sous-dossiers vides
  conservés**, `ZIP_STORED` sur `jpg jpeg png gif mp4 stl 3mf zip` et `ZIP_DEFLATED` sinon ;
  mot de passe lu de `DATABACKUP_ZIP_PASSWORD`/`.env`, absent → **échec sans écriture**.
  **15 tests** ajoutés (AES-256, stocké/dégonflé, chemins relatifs, dossiers vides, source
  intacte, fichier illisible ignoré). Run réel sur 3 dossiers : **4 archives, 151 Mo, 0
  erreur**. Incohérence du CDC §10 corrigée (sous-dossiers vides conservés).

## I4 — Transfert vers Proton Drive ✅ **FAIT** (2026-10-18)

- **Objectif** : envoyer les archives vers `/my-files/databackup`.
- **Livrable** : étape `transfer` : un `upload` par archive (`-f replace`), reprise après
  `auth login` **uniquement dans un terminal** (code `4` sans TTY), **échec compté sans
  interrompre le run**, récapitulatif des échecs.
- **DoD** : tests avec une **doublure** de `proton-drive` (succès, échec compté et run qui
  continue, retry après login en TTY, échec sans TTY avec le code `4`, binaire absent) ; puis
  un **transfert réel** avec `--limit N` sur quelques dossiers non critiques.
- **Résultat** : `transfer` = un `upload -f replace` par archive ; échec **compté sans
  interrompre** ; en terminal, **une** tentative d'`auth login` + reprise ; **hors terminal →
  code `4`** ; binaire absent → code `1` ; rien n'est jamais supprimé côté distant.
  **9 tests** avec une **doublure** (aucun réseau). **Transfert réel** : `all --limit 3` →
  **4 archives, 151 Mo** envoyées en 35 s, `backup/` vidé, code `0` ; **aller-retour vérifié**
  (téléchargement de `documents.zip` puis déchiffrement : 8 fichiers lus).

## I5 — Enchaînement complet, nettoyage et récapitulatif ✅ **FAIT** (2026-10-18)

- **Objectif** : une exécution complète fiable, du scan au nettoyage.
- **Livrable** : commande `all` par défaut (scan → archive → transfer → cleanup), nettoyage
  garanti **même en cas d'échec**, code de sortie fiable (`0` / `1`), récapitulatif final
  affiché et journalisé (archives, volume, échecs).
- **DoD** : test d'un run complet sur données factices ; **aucun résidu dans `backup/`** après
  un succès, après un échec de transfert simulé **et après un `SIGTERM`** ; puis **premier run
  réel complet lancé à la main** (terminal, sans timeout) pour mesurer la durée — en
  particulier l'upload de `Photos.zip` (~3,2 Go) — et ajuster le `timeout` du bouton Piloter
  si besoin.
- **Résultat (code)** : **récapitulatif final** (archives prévues/créées, volume, envoyées,
  échecs de transfert, durée, code retour) affiché et journalisé ; **vidage de `backup/`
  garanti** par un `finally` en fin de `all`/`cleanup` — succès, échec de scan, échec de
  transfert, `SIGTERM`. **3 tests** ajoutés (résidu après échec de transfert, résidu après
  échec de scan, contenu du récapitulatif) ; le cas `SIGTERM` était déjà couvert.
- **Correctif (run réel du 2026-10-18)** : un fichier daté **1979** (2 dans `Prusa`) faisait
  échouer **tout** le run — `ValueError` « ZIP does not support timestamps before 1980 », non
  rattrapée. Corrigé : date **ramenée à 1980** (`strict_timestamps=False`) avec **avertissement**
  (le fichier est conservé), **comptage incrémental** des archives (récapitulatif juste même en
  cas d'échec partiel), et erreur d'un fichier seul → **ignoré sans interrompre**. **3 tests**
  de régression (**77** au total). Règle consignée au CDC §6 ; correctif revalidé sur `Prusa`.
- **✅ Run réel complet** (2026-10-18, lancé à la main) : **14:25** pour **22 archives**
  (4,63 Go créés, 22 envoyés, **0 échec**), `backup/` vidé, code retour `0` ; `photos.zip`
  (3,19 Go) archivé en 11 s et **envoyé en 9:01**, `prusa.zip` en 1:41. Le `timeout` Piloter
  de **1 h est confirmé** (large marge). Côté Proton : **22 archives uniques**, aucune orpheline.

## I6 — Documentation utilisateur (`README.md`) ✅ **FAIT** (2026-10-18)

- **Objectif** : quelqu'un qui découvre le dossier peut installer et lancer la sauvegarde.
- **Livrable** : `README.md` — prérequis, `./install.sh`, création de `.env` (mot de passe),
  création de la destination Proton, commandes et options, codes retour, emplacement des logs,
  usage manuel **et** via Piloter.
- **DoD** : les commandes du README sont rejouables telles quelles ; il renvoie au `cdc.md` §10
  pour la restauration (**hors v1**).
- **Résultat** : `README.md` complet — principe, prérequis, installation (`./install.sh`,
  symlinks `source/`/`backup/`, `.env`, connexion Proton, création de la destination),
  utilisation (commandes, options, codes retour, enchaînements), journalisation, annulation,
  usage Piloter, renvoi au `cdc.md` §10 (**restauration hors v1**), dépannage, développement.
  **Aucun chemin personnel** (règle `AGENTS.md`) ; commandes vérifiées rejouables (`--help`,
  `scan`, argument invalide → code `2`).

---

## Backlog (hors v1 — ne pas coder sans décision actée au CDC §13)

- **Piloter** (autre dépôt) : adaptateur `piloter/scripts/databackup-start.sh` + bouton
  déclencheur « Sauvegarde docs » (`confirm: true`, `timeout: 3600`) — sur demande de Yves ;
- **restauration** (hors v1, cf. `cdc.md` §10 et §13) : écrire la procédure, la **tester
  réellement depuis Proton Drive** (téléchargement + déchiffrement), puis éventuellement une
  commande `./start.sh restore` ;
- historique daté côté distant (au lieu du miroir de l'état courant) ;
- sauvegarde incrémentale (n'envoyer que ce qui a changé) ;
- notification de fin (mail ou notification bureau) ;
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

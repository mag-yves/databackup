# DataBackup

Sauvegarde **hors site** des documents : une **archive zip chiffrée AES-256 par dossier** de
premier niveau, envoyée sur **Proton Drive**. Script **Python** exécuté en local, sans
synchronisation bidirectionnelle. La référence fonctionnelle est le cahier des charges
[`cdc.md`](cdc.md).

## Principe

- `source/` est lu **en lecture seule** : jamais modifié, déplacé ni supprimé.
- Chaque **dossier de premier niveau** donne une archive (`Photos` → `photos.zip`, …) ; les
  fichiers posés à la racine vont dans **`documents.zip`**.
- Les archives sont **chiffrées AES-256** avec un **mot de passe unique**, et **envoyées** vers
  `/my-files/databackup` (une archive distante de même nom est **écrasée**).
- **Rien n'est jamais supprimé côté distant** : les archives d'anciens dossiers sont conservées
  (à nettoyer à la main).
- **Sauvegarde incrémentale** (cf. §« Incrémental ») : seuls les dossiers **modifiés** sont
  recompressés et renvoyés ; un dossier **sans historique est toujours inclus**.
- Un run **écrase** l'état précédent côté Proton — ce n'est pas un historique daté.

## Incrémental — ne refaire que ce qui a changé

Chaque run compare les dossiers à un **historique local** (`.databackup-state.json`, non
versionné, sans secret) et ne recompresse puis ne renvoie que les **nouveaux** ou **modifiés**.
Concrètement :

- la comparaison se fait sur les **métadonnées** (chemin, taille, date de modification, plus les
  sous-dossiers vides) : le contenu des fichiers n'est **jamais relu** ;
- l'historique n'est mis à jour qu'**après un upload réussi** : un transfert en échec est
  simplement retenté au run suivant ;
- **tout ce qui n'est pas prouvé à jour est sauvegardé** : pas d'historique (premier run,
  `git clone` neuf, fichier supprimé), historique illisible, dossier renommé → sauvegarde
  **complète**. Perdre l'historique ne peut donc jamais faire *manquer* une sauvegarde ;
- `./start.sh all --full` ignore l'historique et refait **tout** (dépannage, après une
  restauration) ;
- limites assumées : un fichier modifié en conservant **taille et date** n'est pas détecté, et
  une archive supprimée **à la main** sur Proton ne sera pas renvoyée (cf. `cdc.md` §6).

## Prérequis

- Linux, **Python ≥ 3.10**.
- `curl` ou `wget` (pour `./install.sh`).
- Un **compte Proton Drive** ; le CLI `proton-drive` est téléchargé par `./install.sh`.
- Un dossier de documents à sauvegarder (lecture seule) et un dossier temporaire sur un disque
  avec **≈ 5 Go libres** (le volume des archives).

## Installation

1. Récupérer le projet, puis se placer dans son dossier.

2. **Binaire Proton Drive** (non versionné) :

   ```bash
   ./install.sh
   ```

3. **Liens vers les dossiers de la machine** (propres à la machine, non versionnés) :

   ```bash
   ln -s /chemin/vers/mes/documents source
   ln -s /chemin/vers/disque/backup backup
   ```

   `source/` = les documents à sauvegarder ; `backup/` = dossier **temporaire** (vidé à chaque
   run), sur un disque disposant de la place.

4. **Mot de passe des archives** — fichier `.env` local (non versionné) :

   ```bash
   printf 'DATABACKUP_ZIP_PASSWORD=%s\n' 'votre-mot-de-passe' > .env
   chmod 600 .env
   ```

   ⚠️ **Sans ce mot de passe, les archives sont irrécupérables** : conservez-le dans votre
   gestionnaire de mots de passe. La variable d'environnement `DATABACKUP_ZIP_PASSWORD` est
   prioritaire sur `.env`.

5. **Connexion Proton** (une seule fois ; ouvre le navigateur, donc interactive) :

   ```bash
   ./proton-drive auth login
   ./proton-drive filesystem create-folder /my-files databackup   # si le dossier n'existe pas
   ```

6. **Vérification** (n'écrit rien, n'envoie rien) :

   ```bash
   ./start.sh scan
   ```

## Utilisation

```bash
./start.sh [scan|archive|transfer|cleanup|all] [options]
```

| Commande | Effet |
|---|---|
| `scan` | Affiche le plan : dossiers **nouveaux / modifiés / inchangés**, noms d'archives, volume estimé — **n'écrit rien**. |
| `archive` | Crée dans `backup/` les archives chiffrées **des dossiers nouveaux ou modifiés** (dossier vidé **avant**). |
| `transfer` | Envoie les archives de `backup/` vers Proton Drive, puis met à jour l'historique. |
| `cleanup` | Vide `backup/`. |
| `all` | `scan` → `archive` → `transfer`, puis vide `backup/` (**défaut**). |

| Option | Effet |
|---|---|
| `--dry-run` | Affiche le plan sans rien écrire dans `backup/` ni rien envoyer. |
| `--limit N` | Ne traite que les **N premiers dossiers** (`scan`, `archive`, `all`) — test sans envoyer 5 Go. |
| `--full` | **Ignore l'historique** : refait toutes les archives (`scan`, `archive`, `all`). |

```bash
./start.sh                  # sauvegarde incrémentale (scan → archive → transfert → nettoyage)
./start.sh scan             # que serait-il sauvegardé ?
./start.sh scan --limit 3   # les 3 premiers dossiers seulement
./start.sh all --limit 2    # test réel (archivage + envoi) sur 2 dossiers
./start.sh all --full       # tout refaire, comme si l'historique n'existait pas
./start.sh cleanup          # vide backup/ (déjà vide à la fin d'un « all » réussi)
```

`./start.sh` crée l'environnement virtuel et installe les dépendances au premier lancement.

`archive` seul **laisse** ses archives dans `backup/` (pour un `transfer` ultérieur) ; `all` les
envoie puis **vide** `backup/` quoi qu'il arrive. `scan` seul ne touche à rien.

Un run courant n'envoie donc **que ce qui a changé** : la première fois tout part, ensuite
quelques secondes suffisent si rien n'a bougé. L'historique vit dans `.databackup-state.json`
(racine du projet, non versionné) : le supprimer est **sans danger**, le run suivant sera
simplement complet.

## Codes retour

| Code | Signification |
|---|---|
| `0` | Succès complet. |
| `1` | Échec générique : archivage, transfert, ou collision de noms d'archives. |
| `2` | Argument invalide. |
| `3` | Dossier `backup/` indisponible (disque non monté ?). |
| `4` | Authentification Proton requise — lancez `./proton-drive auth login` dans un terminal. |
| `5` | Sauvegarde déjà en cours (verrou `.databackup.lock`). |

## Journalisation

- Un fichier par exécution : `logs/databackup-<horodatage>.log` ; les **7 derniers** conservés.
- La sortie s'affiche aussi sur le terminal, ligne à ligne : étape, compteur `[n/total]`, nom
  d'archive, taille, durée, puis un **récapitulatif final** (archives, volume, échecs, durée).
- En incrémental, le scan liste les dossiers **inchangés** (avec la date du dernier transfert) et
  le récapitulatif ajoute « Archives ignorées (déjà à jour) : N ».
- Le mot de passe **n'apparaît jamais** dans les logs ni dans la sortie.

## Annulation

Sur `SIGTERM` / `SIGINT` (timeout, `Ctrl-C`) : arrêt propre — le transfert en cours est
interrompu, `backup/` est vidé, le verrou est libéré. Il suffit de relancer.

## Utilisation via Piloter

`start.sh` est le **lanceur unique** du projet et respecte le contrat de Piloter : exécutable
sans terminal, codes retour exploitables, sortie ligne à ligne, annulable.

- Adaptateur (dépôt Piloter) : `piloter/scripts/databackup-start.sh`, simple `exec` vers ce
  `start.sh` *(à créer — cf. backlog de `TODO.md`)*.
- Bouton « Sauvegarde docs » : `confirm: true`, **`timeout: 3600` (1 h)** — un run complet à
  froid a été mesuré à **14:25**, la marge est confortable.
- Sans terminal, `auth login` est impossible : si la session Proton a expiré, le run échoue avec
  le code **`4`** et indique la commande à lancer. Se connecter une fois dans un terminal, puis
  relancer.

## Restauration — hors v1

La v1 ne fournit **ni procédure ni outil** de restauration (cf. [`cdc.md`](cdc.md) **§10**).
Les archives sont des **zip AES-256 standard**, ouvrables avec le mot de passe :

```bash
./proton-drive filesystem download /my-files/databackup/photos.zip .
# puis extraire photos.zip avec 7-Zip (ou pyzipper) et le mot de passe des archives
```

## Dépannage

- **Code `5`** (« déjà en cours ») : un run tourne, ou un verrou est resté après un `kill -9`.
  Un verrou laissé par un processus disparu est **repris automatiquement** au lancement suivant.
- **Code `3`** : le disque de `backup/` n'est pas monté (ou le lien `backup` est cassé).
- **« Aucune archive à créer » / lignes « [inchangé] »** : c'est l'incrémental qui fonctionne —
  ces dossiers sont identiques à leur dernière sauvegarde **réussie**. Pour tout refaire :
  `./start.sh all --full`.
- **« Historique illisible »** : `.databackup-state.json` est corrompu ; il est ignoré et le run
  est **complet** (l'historique est réécrit à la fin). Le supprimer donne exactement le même
  effet, sans risque.
- **« Manifeste absent pour N archive(s) »** : `transfer` a envoyé des archives dont il ne
  connaissait pas la signature (archives copiées à la main dans `backup/`, ou manifeste effacé) :
  rien n'est enregistré, elles seront refaites. Utiliser `all`, ou `archive` puis `transfer` dans
  la même exécution.
- **« date de modification hors plage ZIP »** : un fichier est daté avant 1980 ; il est archivé
  avec la date ramenée à 1980 (le fichier est conservé).
- **« Lien symbolique ignoré »** : les liens internes ne sont pas suivis (choix de conception).
- **Aucune progression pendant un gros upload** : la sortie de `proton-drive` est journalisée à
  la fin de chaque archive (pas de progression fichier par fichier).

## Développement

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest      # suite de tests
.venv/bin/ruff check .          # lint
```

Le module principal est `databackup.py` ; les tests sont dans `tests/`.

## Documentation

- [`cdc.md`](cdc.md) — cahier des charges (source de vérité fonctionnelle).
- [`memory.md`](memory.md) — état courant du projet.
- [`TODO.md`](TODO.md) — itérations et backlog.
- [`usage-proton-drive-cli.md`](usage-proton-drive-cli.md) — aide du CLI `proton-drive`.

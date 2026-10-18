# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** : à lire en début de session et à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 (documents, suivi du temps, `install.sh` repris
  d'`autobackup`) ; **CDC v1 figé** — lots A, B et C tranchés (récap au §12 du CDC).
- **Aucun code** : la prochaine étape est **I1** (socle technique + `start.sh`).
  Dépôt `git@github.com:mag-yves/databackup.git`, branche `main`.

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule** ; `backup/` →
  `/media/yves/SSDBCK/temp/backup` — **vidé au début et à la fin de chaque run** (succès,
  échec ou annulation).
- **Un zip par dossier de premier niveau** ; fichiers racine → **`documents.zip`** ; **AES-256**,
  nommage **normalisé** (collision = échec du scan), `ZIP_STORED` pour les formats compressés,
  **aucun filtrage**, liens symboliques ignorés (détail : §3 et §4 du CDC).
- Mot de passe dans **`.env` local non versionné** (priorité à `DATABACKUP_ZIP_PASSWORD`) ;
  `proton-drive` installé par `./install.sh`.
- Destination **`/my-files/databackup`**, `upload -f replace` (**écrasement**) ; orphelines
  **conservées** ; **pas de contrôle de quota** (CLI muet) ; upload en échec → **on continue**.
- `start.sh` (I1) : lanceur **unique** compatible Piloter (sans TTY, codes retour, annulable),
  **verrou `.databackup.lock`**, `--dry-run` / `--limit N`, **pas de `auth login` sans TTY**.
- **Hors v1** : restauration reportée (risque assumé, §10) ; **planification exclue** (définitif).

## Dette / points d'attention

- Aucune dette (pas de code) ; à **ne pas hériter** d'`autobackup` : mot de passe en dur.
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 **I1 — socle technique** : `start.sh` conforme au §8 (verrou, codes retour, `--dry-run` /
  `--limit N`, mot de passe lu dans `.env`), `pyproject.toml`, module principal + logging.
- 🟠 Le premier run réel complet (I5) mesurera la durée et validera `Photos.zip` (~3,2 Go).

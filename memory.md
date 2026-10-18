# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (lots A, B et C tranchés — récap au §12 du CDC) ; projet
  initialisé (documents, suivi du temps, `install.sh` repris d'`autobackup`), **aucun code**.
- Prochain jalon : **I1 — socle technique** (cf. `TODO.md`). Dépôt
  `git@github.com:mag-yves/databackup.git`, branche `main`.

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue** ; `backup/` →
  `/media/yves/SSDBCK/temp/backup`, **vidé au début et à la fin de chaque run** (succès,
  échec ou annulation ; `scan`/`archive` seuls le laissent en place) — §3, §6.
- **Un zip par dossier de premier niveau** ; fichiers racine → **`documents.zip`** ;
  **AES-256**, nommage **normalisé**, `ZIP_STORED` sur les formats compressés, **aucun
  filtrage** — §3, §4.
- Mot de passe dans **`.env` local non versionné** (priorité à `DATABACKUP_ZIP_PASSWORD`) ;
  `proton-drive` installé par `./install.sh` — §7.
- Destination **`/my-files/databackup`**, `upload -f replace` (**écrasement**) ; orphelines
  **conservées** ; **pas de contrôle de quota** ; upload en échec → **on continue** — §5, §6.
- `start.sh` (I1) : lanceur **unique**, compatible Piloter (sans TTY, codes retour, annulable),
  **verrou `.databackup.lock`**, `--dry-run` / `--limit N`, **pas de `auth login` sans TTY** — §8.
- **Hors v1** : restauration reportée (risque assumé — §10) ; planification **exclue** — §2, §8.

## Dette / points d'attention

- Aucune dette (pas de code) ; à **ne pas hériter** d'`autobackup` : mot de passe en dur.
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 **I1 — socle technique** : `start.sh` conforme au §8, `pyproject.toml`, module + logging.
- 🟠 Le premier run réel complet (I5) mesurera la durée et validera `Photos.zip` (~3,2 Go).

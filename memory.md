# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (récap §12) ; **I1 — socle technique livré** le 2026-10-18 :
  `start.sh`, `databackup.py` (squelette sans logique métier — `scan`/`archive`/`transfer`
  journalisent et sortent en 0), `pyproject.toml`, `requirements*.txt`, 26 tests verts,
  `ruff` propre. Dépôt `git@github.com:mag-yves/databackup.git`, branche `main`.
- Prochain jalon : **I2 — scan des sources** (cf. `TODO.md`).

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue** ; `backup/` →
  `/media/yves/SSDBCK/temp/backup`, **vidé au début et à la fin de chaque run** (`scan`/
  `archive` seuls le laissent en place) — §3, §6.
- **Un zip par dossier de premier niveau** + **`documents.zip`** (fichiers racine) ; **AES-256**,
  nommage **normalisé**, `ZIP_STORED` sur les formats compressés, **aucun filtrage** — §3, §4.
- Mot de passe dans **`.env`** non versionné (priorité `DATABACKUP_ZIP_PASSWORD`) ; destination
  **`/my-files/databackup`**, `upload -f replace`, orphelines **conservées**, **pas de quota**,
  échec d'upload → **on continue** — §5, §7.
- **I1** : `start.sh` fait `exec` du module (groupe de processus préservé) ; le **verrou**
  `.databackup.lock` est tenu par le module (repris s'il est obsolète) ; **`--dry-run`** ne
  touche ni `backup/` ni Proton (log et verrou restent, opérationnels) ; `--limit` sur
  `scan`/`archive`/`all` ; le secret n'est **jamais** journalisé (seule sa provenance l'est).
- **Hors v1** : restauration reportée (risque assumé — §10) ; planification **exclue** — §2, §8.

## Dette / points d'attention

- Aucune dette de code ; `pyzipper` est installé mais **inutilisé** jusqu'à I3.
- ⚠️ Ne pas hériter d'`autobackup` : mot de passe en dur (dette connue, à ne pas reproduire).
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 **I2 — scan des sources** : dossiers retenus/exclus/vides, volume, noms d'archives
  normalisés, détection des collisions (échec du scan) ; **aucune écriture** dans `source/`.
- 🟠 Le premier run réel complet (I5) mesurera la durée et validera `Photos.zip` (~3,2 Go).

# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (récap §12). **I1** (socle) et **I2** (`scan`) **livrés** :
  `./start.sh scan` construit le plan (**22 archives**, **4,70 Go** sur la source réelle) ;
  **47 tests** verts, `ruff` propre. Dépôt `git@github.com:mag-yves/databackup.git`, `main`.
- Prochain jalon : **I3 — création des archives** (cf. `TODO.md`).

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule absolue** ; `backup/` **vidé au début et à la fin de chaque run**
  (`scan`/`archive` seuls le laissent en place) — §3, §6.
- Un zip par dossier de premier niveau + `documents.zip` (fichiers racine) ; **AES-256**,
  nommage normalisé, `ZIP_STORED` sur les formats compressés, aucun filtrage — §3, §4.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD`), jamais journalisé ;
  destination `/my-files/databackup` en `upload -f replace`, orphelines conservées, pas de
  quota, échec d'upload → **on continue** — §5, §7.
- **I1/I2** : `start.sh` fait `exec` du module ; verrou `.databackup.lock` tenu par le module
  (repris s'il est obsolète) ; `scan` = plan seul (dossiers vides exclus, liens ignorés +
  avertis, **collision → échec** code `1`) ; `--limit N` (fichiers racine inclus), `--dry-run`.

## Dette / points d'attention

- Aucune dette de code ; `pyzipper` installé mais **inutilisé** jusqu'à I3.
- ⚠️ Ne pas hériter d'`autobackup` : mot de passe en dur (dette connue).
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 **I3 — archives** : zips AES-256 dans `backup/` (nommage, arborescence interne fidèle §4).
- 🟠 Transfert réel (I4/I5) : prérequis `./install.sh`, `.env`, connexion Proton interactive,
  dossier `/my-files/databackup` ; premier run complet pour mesurer `Photos.zip` (~3,2 Go).

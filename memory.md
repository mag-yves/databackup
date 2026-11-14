# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **I1–I7 livrés et vérifiés** : run complet du 2026-10-18 en **14:25** (22 archives, 4,63 Go,
  0 échec), `timeout` Piloter de 1 h confirmé ; incrémental I7 rejoué (18:29, puis 0,2 s —
  22 archives ignorées), **110 tests** verts (`cdc.md` §6, §12 lot D).
- **I8 livré** (2026-11-14) : `config.local` remplace les symlinks `source`/`backup` — **117
  tests** verts, `ruff` propre ; chemins absolus, échec explicite (code `1`) sinon ; zips
  temporaires dans `/media/yves/SSDBCK/temp/databackup`.

## Décisions actées (détail au CDC §3–§8)

- **Chemins machine dans `config.local`** (non versionné, `KEY=valeur`) : `SOURCE_DIR` **lecture
  seule** ; `BACKUP_DIR` **vidé au début et à la fin de chaque run** ; **aucun symlink**. Un zip
  **AES-256** par dossier de premier niveau + `documents.zip` (racine) ; nommage normalisé,
  `ZIP_STORED` sur les formats compressés, aucun filtrage ; `/my-files/databackup`
  (`upload -f replace`), orphelines gardées.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais journalisé ; échec d'upload → **on continue**.
- **I7 — incrémental** : signature `sha256` (chemin + taille + mtime, contenu jamais relu) ;
  historique `.databackup-state.json` (atomique) mis à jour **après un upload réussi**
  seulement, signature portée par le **manifeste** ; **défaut sûr** (sans historique = complet).

## Dette / points d'attention

- Aucune dette de code ; ⚠️ pas de mot de passe en dur ; ⚠️ `SOURCE_DIR` **synchronisé par kDrive**.
- ⚠️ Incrémental (§6) : modification **conservant taille et date** non vue ; archive **supprimée
  à la main** sur Proton non renvoyée ; historique **jamais purgé**.
- ⚠️ `transfer` : **silence de 9 min** constaté sur `photos.zip` — pas de progression
  **intra-upload** (§9).

## Prochaines actions

- 🔴 Backlog (`TODO.md`) : **Piloter**, **restauration**, **hygiène de l'historique**,
  progression intra-upload, historique daté.

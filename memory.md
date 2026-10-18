# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **I1 à I6 livrés et vérifiés** : run complet du 2026-10-18 en **14:25** (22 archives, 4,63 Go,
  0 échec), `timeout` Piloter de 1 h confirmé (`cdc.md` §12).
- **I7 livré et vérifié** (2026-10-18) : **sauvegarde incrémentale** (`cdc.md` §6, §12 lot D) —
  **110 tests** verts, `ruff` propre, `README.md` à jour. Réel : run complet **18:29** (19
  archives, 4,49 Go, 0 échec) puis run suivant **0,2 s** — **22 archives ignorées**, rien renvoyé.

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule** ; un zip **AES-256** par dossier de premier niveau + `documents.zip`
  (racine) ; nommage normalisé, `ZIP_STORED` sur les formats compressés, aucun filtrage ;
  `backup/` **vidé au début et à la fin de chaque run** (`scan`/`archive` seuls le laissent, avec
  le manifeste) ; `/my-files/databackup` (`upload -f replace`), orphelines conservées.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais journalisé ; échec d'upload → **on continue**.
- **I7 — incrémental** : signature `sha256` (chemin + taille + mtime ; contenu jamais relu) ;
  historique `.databackup-state.json` (non versionné, atomique) mis à jour **après un upload
  réussi** seulement ; signature portée par le **manifeste** temporaire du run ; **défaut sûr**
  (pas d'historique = complet) ; `--full` ; `--limit` n'inscrit que le traité.
- **I1–I5** (socle, `scan`, `archive`, `transfer`, `all`) : détail au `cdc.md` §12 — inchangés par I7.

## Dette / points d'attention

- Aucune dette de code ; ⚠️ pas de mot de passe en dur ; ⚠️ `source` **synchronisé par kDrive**.
- ⚠️ Incrémental (§6) : modification **conservant taille et date** non vue ; archive **supprimée à
  la main** sur Proton non renvoyée ; historique **jamais purgé**.
- ⚠️ `transfer` : **silence de 9 min** constaté sur `photos.zip` — pas de progression
  **intra-upload** (§9).

## Prochaines actions

- 🔴 Backlog (`TODO.md`) : **Piloter**, **restauration**, **hygiène de l'historique**,
  progression intra-upload, historique daté.

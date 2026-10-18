# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé et intégralement vérifié en réel** (récap §12). **I1 à I6 livrés** (`all` =
  scan → archive → transfert → nettoyage, **récapitulatif final**, **`backup/` vidé quoi qu'il
  arrive**) ; **77 tests** verts, `ruff` propre ; `README.md` complet.
- **Run réel complet** (2026-10-18) : **14:25**, **22 archives** (4,63 Go, **0 échec**),
  `photos.zip` (3,19 Go) en 9:01 ; `timeout` Piloter **1 h confirmé** ; 22 archives uniques
  côté Proton. Prérequis prêts : `proton-drive` 0.9.0, session active, destination, `.env`.
- **La v1 est terminée** ; la suite est au backlog de `TODO.md` (Piloter, restauration…).

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule** ; un zip **AES-256** par dossier de premier niveau + `documents.zip`
  (racine) ; nommage normalisé, `ZIP_STORED` sur les formats compressés, aucun filtrage ;
  `backup/` **vidé au début et à la fin de chaque run** (`scan`/`archive` seuls le laissent) ;
  destination `/my-files/databackup` (`upload -f replace`), orphelines conservées.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais journalisé ; échec d'upload → **on continue**.
- **I1–I5** : `exec` + verrou `.databackup.lock` (repris si obsolète) ; `scan` = plan seul
  (**collision → échec** `1`) ; `archive` = vidage avant, sous-dossiers vides conservés,
  **date hors plage ZIP ramenée à 1980** (§6) ; `transfer` = `upload -f replace`, échec
  **compté**, login + reprise **en TTY seulement** (**code `4`** sinon) ; `all` = chaîne
  complète + **vidage final garanti** (succès, échec, annulation) + **récapitulatif** ;
  `--limit N`, `--dry-run`.

## Dette / points d'attention

- Aucune dette de code ; ⚠️ pas de mot de passe en dur (contrairement à `autobackup`) ; ⚠️
  `source` est **synchronisé par kDrive** (il peut bouger pendant une exécution).
- ⚠️ `transfer` capture la sortie de `proton-drive` : **silence de 9 min** constaté sur
  `photos.zip` — pas de progression **intra-upload** (CDC §9, amélioration possible).

## Prochaines actions

- 🔴 Backlog (cf. `TODO.md`) : **Piloter** (adaptateur `databackup-start.sh` + bouton
  déclencheur, voire statut « en cours »), **restauration** (hors v1), progression
  **intra-upload**, historique daté.

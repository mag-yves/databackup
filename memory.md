# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (récap §12). **I1 à I5 (code) livrés** : `all` enchaîne
  scan → archive → transfert → nettoyage, avec **récapitulatif final** et **`backup/` vidé quoi
  qu'il arrive** ; **77 tests** verts, `ruff` propre. Transfert réel validé (I4) ; 1er run
  complet interrompu par un bug **corrigé** (fichiers datés 1979 → date ramenée à 1980, CDC §6)
  ; **à relancer**.
- Prérequis prêts : `proton-drive` 0.9.0, session Proton active, dossier `/my-files/databackup`.
- Prochain jalon : premier run réel complet, puis **I6 — `README.md`**.

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule** ; un zip **AES-256** par dossier de premier niveau + `documents.zip`
  (racine) ; nommage normalisé, `ZIP_STORED` sur les formats compressés, aucun filtrage ;
  `backup/` **vidé au début et à la fin de chaque run** (`scan`/`archive` seuls le laissent).
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais journalisé ; destination `/my-files/databackup`
  (`upload -f replace`), orphelines conservées, échec → **on continue**.
- **I1–I5** : `exec` + verrou `.databackup.lock` (repris si obsolète) ; `scan` = plan seul
  (**collision → échec** `1`) ; `archive` = vidage avant + sous-dossiers vides conservés ;
  `transfer` = `upload -f replace`, échec **compté**, login + reprise **en TTY seulement**
  (**code `4`** sinon) ; `all` = chaîne complète, **vidage final garanti** (succès, échec,
  annulation) et **récapitulatif** journalisé ; `--limit N`, `--dry-run`.

## Dette / points d'attention

- Aucune dette de code ; ⚠️ pas de mot de passe en dur (contrairement à `autobackup`).
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.
- ⚠️ `transfer` capture la sortie de `proton-drive` : pas de progression **intra-upload**
  (à réévaluer sur `Photos.zip` ~3,2 Go).

## Prochaines actions

- 🔴 **Premier run réel complet** (à la main, sans timeout) : mesurer la durée, surtout
  `Photos.zip` (~3,2 Go) ; ajuster ensuite le `timeout` du bouton Piloter (CDC §8).
- 🔴 **I6 — `README.md`** : installation, `.env`, destination Proton, commandes, codes retour.

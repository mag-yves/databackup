# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (récap §12). **I1 à I4 livrés** ; `all --limit 3` **réel** →
  4 archives (**151 Mo**) AES-256 envoyées sur `/my-files/databackup` en 35 s, aller-retour
  déchiffré OK ; **71 tests** verts, `ruff` propre. Prérequis prêts : `proton-drive` 0.9.0,
  session Proton active, dossier de destination créé.
- Prochain jalon : **I5 — enchaînement complet, nettoyage et récapitulatif** (cf. `TODO.md`).

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule** ; un zip **AES-256** par dossier de premier niveau + `documents.zip`
  (racine) ; nommage normalisé, `ZIP_STORED` sur les formats compressés, aucun filtrage ;
  `backup/` **vidé au début et à la fin de chaque run** (`scan`/`archive` seuls le laissent) —
  §3, §4, §6.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais journalisé ; destination `/my-files/databackup`
  (`upload -f replace`), orphelines conservées, échec → **on continue** — §5, §7.
- **I1–I4** : `exec` + verrou `.databackup.lock` (repris si obsolète) ; `scan` = plan seul
  (**collision → échec** `1`) ; `archive` = vidage avant + sous-dossiers vides conservés ;
  `transfer` = `upload -f replace`, échec **compté**, login + reprise **en TTY seulement**
  (**code `4`** sinon) ; `--limit N`, `--dry-run`.

## Dette / points d'attention

- Aucune dette de code ; ⚠️ pas de mot de passe en dur (contrairement à `autobackup`).
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.
- ⚠️ `transfer` capture la sortie de `proton-drive` : pas de progression **intra-upload**
  (à réévaluer sur `Photos.zip` ~3,2 Go).

## Prochaines actions

- 🔴 **I5 — enchaînement complet** : récapitulatif final, nettoyage garanti même en échec ou
  annulation ; puis **I6 — `README.md`**.
- 🟠 **Premier run réel complet** (à la main, sans timeout) pour mesurer `Photos.zip` (~3,2 Go).

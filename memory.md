# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** — à lire en début de session, à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- **CDC v1 figé** le 2026-10-18 (récap §12). **I1 à I3 livrés** (socle, `scan`, `archive`) :
  `archive --limit 3` réel → 4 zips **AES-256** (**151 Mo**, 0 erreur) ; **62 tests** verts,
  `ruff` propre.
- Prochain jalon : **I4 — transfert vers Proton Drive** (cf. `TODO.md`).

## Décisions actées (détail au CDC §3–§8)

- `source/` **lecture seule** ; `backup/` **vidé au début et à la fin de chaque run**
  (`scan`/`archive` seuls le laissent) ; un zip par dossier de premier niveau + `documents.zip`
  (fichiers racine) ; **AES-256**, nommage normalisé, `ZIP_STORED` sur les formats compressés,
  aucun filtrage — §3, §4, §6.
- Mot de passe dans **`.env`** (priorité `DATABACKUP_ZIP_PASSWORD` ; **en clair au CDC §4**,
  exception assumée §11), jamais dans le code, les logs ni la sortie ; destination
  `/my-files/databackup` (`upload -f replace`), orphelines conservées, échec → **on continue**.
- **I1–I3** : `exec` du module, verrou `.databackup.lock` (repris si obsolète) ; `scan` = plan
  seul (**collision → échec** code `1`) ; `archive` vide `backup/` avant d'écrire et conserve
  les sous-dossiers vides ; `--limit N`, `--dry-run` ; mot de passe absent → échec sans écriture.

## Dette / points d'attention

- Aucune dette de code ; ⚠️ ne pas hériter d'`autobackup` (mot de passe en dur).
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 **I4 — transfert** : un `upload -f replace` par archive, échec compté sans interrompre le
  run, reprise après `auth login` **seulement en TTY** (code `4` sinon).
- 🟠 Prérequis du transfert réel : `./install.sh`, `.env`, connexion Proton interactive, dossier
  `/my-files/databackup` ; premier run complet pour mesurer `Photos.zip` (~3,2 Go).

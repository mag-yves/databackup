# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions** : à lire en début de session et à mettre à jour
> après tout changement significatif. Règles, structure et pièges : `AGENTS.md` ; détail
> fonctionnel : `cdc.md`. **Ne rien dupliquer ici.** Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 (documents, suivi du temps, `install.sh` repris
  d'`autobackup`) ; **aucun code** : le CDC est en cours de rédaction.
- Phase **analyse** : socle, **lots A et B** et contrat `start.sh`/Piloter tranchés ; reste le
  **lot C** (`cdc.md` §12). Dépôt `git@github.com:mag-yves/databackup.git`, branche `main`.

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue** ; `backup/` →
  `/media/yves/SSDBCK/temp/backup` (temporaire, vidé avant et après).
- **Un zip par dossier de premier niveau** ; fichiers racine → **`documents.zip`** ; **AES-256**,
  nommage **normalisé**, `ZIP_STORED` pour les formats compressés, **aucun filtrage**, liens
  symboliques ignorés (détail : §3 et §4 du CDC).
- Mot de passe : **`.env` local non versionné** (priorité à `DATABACKUP_ZIP_PASSWORD`), déjà
  dans le gestionnaire de mots de passe ; `proton-drive` via `./install.sh`.
- Destination **`/my-files/databackup`**, `upload -f replace` (**écrasement**) ; orphelines
  **conservées** (rien n'est supprimé côté Proton) ; **aucun contrôle de quota** (CLI muet).
- `start.sh` (I1) : lanceur **unique** compatible Piloter (sans TTY, codes retour, annulable),
  **verrou `.databackup.lock`**, `--dry-run` / `--limit N`, **pas de `auth login` sans TTY**.

## Dette / points d'attention

- Aucune dette (pas de code) ; à **ne pas hériter** d'`autobackup` : mot de passe en dur.
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 Traiter le **lot C** du `cdc.md` §12 : collision de noms, `ZIP_STORED` étendu, reprise après
  échec, vérification post-transfert, kDrive, gros fichier, restauration, planification.
- 🟠 I1 (socle technique) une fois le CDC v1 figé : `start.sh` conforme au §8 (verrou, codes
  retour, `--dry-run` / `--limit N`, mot de passe lu dans `.env`).

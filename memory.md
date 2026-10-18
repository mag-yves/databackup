# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions**, à lire en début de session et à mettre à jour
> après tout changement significatif. Les règles de travail et les pièges sont dans
> `AGENTS.md` ; le détail fonctionnel vit dans `cdc.md`. **Ne rien dupliquer ici.**
> Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 (documents, suivi du temps, `install.sh` repris
  d'`autobackup`) ; **aucun code** : la rédaction du CDC est en cours.
- Phase **analyse** : socle, **lot A** et contrat `start.sh`/Piloter tranchés ; restent les
  **lots B et C** (`cdc.md` §12). Dépôt `git@github.com:mag-yves/databackup.git`, branche `main`.

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue** ; `backup/` →
  `/media/yves/SSDBCK/temp/backup` (temporaire, vidé avant et après).
- **Un zip par dossier de premier niveau** ; fichiers racine → **`documents.zip`** ;
  chiffrement **AES-256** (`proton@zip@protected`), nommage **normalisé**, `ZIP_STORED` pour
  les formats déjà compressés, **aucun filtrage**, liens symboliques ignorés (détail §4 du CDC).
- Destination **`/my-files/databackup`**, `upload -f replace` (**écrasement**, pas d'historique).
- `start.sh` (I1) : lanceur unique **compatible Piloter** (sans TTY, codes retour, sortie
  ligne par ligne, annulable) + **verrou `.databackup.lock`** ; **pas de `auth login` sans TTY**.
- `proton-drive` installé par `./install.sh`, non versionné.

## Dette / points d'attention

- Aucune dette (pas de code). À **ne pas hériter** d'`autobackup` : mot de passe en dur.
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 Traiter les **lots B et C** du `cdc.md` §12 (transfert et secret, puis archive et restitution).
- 🔴 Sortir le **mot de passe zip du code** (env var ou fichier local non versionné) et le
  sauvegarder hors projet.
- 🟠 I1 (socle technique) une fois le CDC v1 figé : `start.sh` conforme au contrat §8.

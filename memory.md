# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions**, à lire en début de session et à mettre à jour
> après tout changement significatif. Les règles de travail, la structure et les pièges sont
> dans `AGENTS.md` ; le détail fonctionnel vit dans `cdc.md`. **Ne rien dupliquer ici.**
> Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 : structure documentaire, suivi du temps (`devtime`),
  `install.sh` et `usage-proton-drive-cli.md` repris du projet de référence `autobackup`.
  **Aucune ligne de code applicatif** pour l'instant.
- Phase : **analyse** — `cdc.md` est rédigé (v1) ; **12 questions ouvertes au §12** restent à
  trancher avec Yves avant que l'on code.
- Dépôt Git : `git@github.com:mag-yves/databackup.git`, branche `main`.

## Décisions actées

- Besoin : sauvegarder mes **documents par dossier** et les envoyer vers **Proton Drive**,
  en réutilisant l'approche d'`autobackup` (CLI `proton-drive`, pas de synchronisation).
- Sources : `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue**
  (21 dossiers de 1er niveau, 2 315 fichiers, ≈ 4,8 Go relevés le 2026-10-18).
- **Un zip par dossier de premier niveau** (récursif) ; les fichiers posés à la racine sont
  groupés dans **`documents.zip`**.
- Chiffrement **AES-256**, mot de passe `proton@zip@protected` (commun avec `autobackup`).
- Dossier temporaire : `backup/` → `/media/yves/SSDBCK/temp/backup`.
- Destination Proton : **`/my-files/databackup`**, `upload -f replace` : **les archives
  distantes de même nom sont écrasées** (un seul état courant, pas d'historique).
- Binaire `proton-drive` téléchargé **dans le projet** par `./install.sh`, non versionné.
- Itérations prévues : `TODO.md` — I1 socle technique → I6 restauration, I0 = analyse/CDC.

## Dette / points d'attention

- Aucune dette technique (pas de code). Dette **à ne pas hériter** d'`autobackup` : mot de
  passe d'archive en dur dans le code.
- ⚠️ `source` est un dossier **synchronisé par kDrive** : le contenu peut bouger pendant une
  exécution ; c'est un point à trancher (cf. `cdc.md` §3).

## Prochaines actions

- 🔴 Trancher les **12 questions du `cdc.md` §12** (priorité : nommage des archives,
  fichiers déjà compressés `ZIP_STORED`, dossiers vides, fichiers temporaires/cachés).
- 🔴 Choisir l'emplacement du **mot de passe zip hors du code** (env var ou fichier local
  non versionné) et le sauvegarder hors projet.
- 🟠 Démarrer I1 (socle technique) une fois le CDC v1 figé.

# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions**, à lire en début de session et à mettre à jour
> après tout changement significatif. Les règles de travail et les pièges sont dans
> `AGENTS.md` ; le détail fonctionnel vit dans `cdc.md`. **Ne rien dupliquer ici.**
> Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 : structure documentaire, suivi du temps, `install.sh` et
  `usage-proton-drive-cli.md` repris d'`autobackup`. **Aucun code applicatif.**
- Phase : **analyse** — `cdc.md` en cours de rédaction : **lot A** (contenu des archives :
  nommage normalisé, `ZIP_STORED`, aucun filtrage, liens ignorés) tranché le 2026-10-18 ;
  restent les **lots B et C** (§12). Dépôt : `git@github.com:mag-yves/databackup.git`, `main`.

## Décisions actées

- `source/` → `/home/yves/kDrive/Personnel`, **lecture seule absolue** (21 dossiers de premier
  niveau, 2 315 fichiers, ≈ 4,8 Go au 2026-10-18) ; `backup/` → `/media/yves/SSDBCK/temp/backup`.
- **Un zip par dossier de premier niveau** (récursif) ; fichiers posés à la racine →
  **`documents.zip`**.
- Chiffrement **AES-256**, mot de passe `proton@zip@protected` (commun avec `autobackup`).
- Destination **`/my-files/databackup`**, `upload -f replace` : **écrasement** des archives
  distantes (état courant seul, pas d'historique).
- `proton-drive` téléchargé dans le projet par `./install.sh`, non versionné.
- Itérations : `TODO.md` — I1 socle technique → I6 restauration ; I0 = analyse/CDC.

## Dette / points d'attention

- Aucun code, donc aucune dette. À **ne pas hériter** d'`autobackup` : mot de passe en dur.
- ⚠️ `source` est **synchronisé par kDrive** : son contenu peut bouger pendant une exécution.

## Prochaines actions

- 🔴 Traiter les **lots B et C** du `cdc.md` §12 : transfert et secret (orphelins, mot de
  passe hors du code, verrou, options de test, quota) puis archive et restitution.
- 🔴 Sortir le **mot de passe zip du code** (env var ou fichier local non versionné) et le
  sauvegarder hors projet.
- 🟠 Démarrer I1 (socle technique) une fois le CDC v1 figé.

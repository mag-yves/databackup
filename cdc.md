# Cahier des charges — DataBackup

> **Source de vérité du projet.** Toute évolution fonctionnelle est écrite et validée ici
> **avant** d'être codée. Les points marqués ⬜ restent à trancher. Les décisions actées sont
> en gras dans les sections concernées ; les questions encore ouvertes sont regroupées au §12.
> Règles de travail : `AGENTS.md` — itérations prévues : `TODO.md`.

## 1. Objectif

Sauvegarder les documents du dossier `source` vers **Proton Drive**, sous forme d'**une
archive zip chiffrée par dossier** de premier niveau. L'objectif est une sauvegarde **hors
site** simple, rejouable à la main, sans synchronisation bidirectionnelle.

## 2. Périmètre

### Dans le périmètre (v1)

- Lecture de **tout** le contenu de `source/` (symlink → `/home/yves/kDrive/Personnel`),
  **en lecture seule** ;
- **un zip chiffré par dossier** de premier niveau sous `source/` ;
- **un zip** `documents.zip` pour les fichiers posés directement à la racine de `source/` ;
- chiffrement **AES-256**, mot de passe unique (cf. §4) ;
- transfert vers **`/my-files/databackup`**, **écrasement** des archives distantes de même
  nom (cf. §5) ;
- exécution **manuelle** via `./start.sh` (cf. §8).

### Hors périmètre (v1)

- historique **daté** côté distant (on écrase : un seul état courant) ;
- sauvegarde **incrémentale** (on refait tous les zips à chaque exécution) ;
- **suppression** côté Proton d'archives dont le dossier source a disparu ⬜ (cf. §5) ;
- restauration **outillée** (v1 : procédure documentée, cf. §10) ;
- planification automatique (cron / systemd) ;
- autres sources (photos hors `source`, dépôts Git, bases de données).

## 3. Sources — quels dossiers ?

| Élément | Décision |
|---|---|
| Racine | `source/` → **`/home/yves/kDrive/Personnel`** (symlink non versionné) |
| Droits | **Lecture seule, absolue** : aucun fichier de `source` n'est modifié, déplacé ou supprimé |
| Unité sauvegardée | **chaque dossier de premier niveau** = une archive, **récursive** (toute la profondeur : jusqu'à 7 niveaux aujourd'hui) |
| Fichiers à la racine | regroupés dans **`documents.zip`** |
| Sous-dossier d'un dossier | inclus dans l'archive du dossier parent (pas d'archive par sous-dossier) |
| Dossiers vides | ⬜ ignorés (aucune archive) ? *(2 dossiers vides détectés aujourd'hui)* |
| Liens symboliques internes | ⬜ suivis ou ignorés ? *(aucun détecté au premier niveau aujourd'hui)* |
| Fichiers temporaires | ⬜ inclus ou exclus ? *(ex. `Compta Homebank.xhb~`)* |
| Fichiers cachés (`.…`) | ⬜ inclus ou exclus ? *(aucun aujourd'hui à la racine)* |
| Fichiers modifiés pendant l'exécution | ⬜ la source est **synchronisée par kDrive** : un fichier peut changer pendant l'archivage — avertir et continuer, ou échouer ? |

**Volumétrie relevée le 2026-10-18** (indicative, pour dimensionner les transferts) :
21 dossiers de premier niveau + 8 fichiers à la racine, **2 315 fichiers**, **≈ 4,8 Go**.
Répartition (ordre décroissant) : `Photos` 3,2 Go · `Prusa` 628 Mo · `Maison` 326 Mo ·
`Voitures` 180 Mo · `Archives` 143 Mo · `Documentations` 91 Mo · `Divers` 49 Mo ·
`Terrains` 44 Mo · `Garanties - modes d'emploi` 40 Mo · `Signature` 18 Mo ·
`Places de camp` 12 Mo · `Complotiste !` 8,6 Mo · `SATOM` 4,4 Mo · `Assurances` 2,4 Mo ·
puis < 400 Ko : `Pictos contacts`, `YM`, `Notes`, `Graines`, `Scripts`, `Skills et modèles IA`,
`Windows blocks`. Fichiers à la racine ≈ 2,3 Mo (5 `.bak` Homebank, `.xhb`, `.xhb~`, un `.odt`).

Extension dominantes : `jpg` (853), `stl` (285), `pdf` (266), `gif` (242), `3mf` (214),
`f3d` (96), `png` (75), `odt` (48), `zip` (30), `mp4` (17).

## 4. Format des archives

**Décidé**

- Format : **zip chiffré AES-256** (`pyzipper`, comme le projet `autobackup`).
- Mot de passe : **`proton@zip@protected`**, unique et commun aux archives.
- Une archive par dossier de premier niveau ; `documents.zip` pour les fichiers racine.
- Écrasement côté Proton (miroir de l'état courant, cf. §5).

**À trancher**

- ⬜ **Nommage** : `<nom du dossier>.zip` à l'identique ? Attention aux noms contenant
  espaces et caractères spéciaux (`Complotiste !`, `Garanties - modes d'emploi`,
  `Skills et modèles IA`). Préfixe commun pour les repérer sur Proton ?
- ⬜ **Fichiers déjà compressés** (`jpg`, `gif`, `png`, `mp4`, `stl`, `3mf`, `zip`…) stockés
  **sans compression** (`ZIP_STORED`) mais chiffrés, comme `autobackup` ? L'enjeu est réel :
  `Photos` (3,2 Go de `jpg`) et `Prusa` (628 Mo de `stl`/`3mf`) gagneraient peu à être
  recompressés, mais coûtent du temps CPU.
- ⬜ **Dossier vide rencontré dans une archive** : conservé ou omis ?
- ⬜ Compression zip : niveau par défaut ?

## 5. Destination et transfert (Proton Drive)

**Décidé**

- Outil : CLI officiel **`proton-drive`**, installé par `./install.sh`, **non versionné**
  (référence : `usage-proton-drive-cli.md`).
- Destination : **`/my-files/databackup`**.
- Un appel `upload` **par archive** :
  `./proton-drive filesystem upload -f replace <archive> /my-files/databackup`
- **`-f replace` = les archives distantes de même nom sont écrasées** par la version locale
  (la version remplacée part dans la corbeille Proton : pas d'historique géré par nous).
- **Authentification hybride** : ni `login` ni `logout` systématique ; en cas d'échec d'un
  upload, tentative d'`auth login` (navigateur, interactif) puis reprise de l'upload.

**À trancher**

- ⬜ **Archives orphelines** (présentes sur Proton, dont le dossier source n'existe plus) :
  on les laisse (recommandé) ou on les supprime (miroir strict) ?
- ⬜ **Quota Proton** : ~4,8 Go aujourd'hui et en croissance — vérifier l'espace disponible
  avant un transfert ? Que faire si insuffisant (échouer, avertir, continuer) ?
- ⬜ **Gros fichier** : `Photos.zip` ≈ 3,2 Go en un seul upload — à valider sur un transfert
  réel (durée, coupures, reprise).
- ⬜ **Coupure réseau en cours de transfert** : reprise, marquage, ou échec complet ?
- ⬜ **Vérification post-transfert** (taille et/ou empreinte comparées) ?

## 6. Processus (déroulé d'une exécution)

1. **Contrôle** — le disque de `backup/` est monté et accessible en écriture, sinon échec
   explicite (`backup/` → `/media/yves/SSDBCK/temp/backup`).
2. **Nettoyage** — `backup/` est **vidé** avant toute chose (il est temporaire).
3. **Scan** — dossiers de premier niveau de `source/` retenus + fichiers racine ; les
   dossiers vides sont écartés ⬜.
4. **Archives** — création des zips chiffrés dans `backup/`.
5. **Transfert** — envoi des zips de `backup/` vers `/my-files/databackup`, un `upload` par
   zip.
6. **Nettoyage final** — `backup/` est vidé **quoi qu'il arrive**, même en cas d'échec.

Points à trancher :

- ⬜ Espace requis : jusqu'à ~4,8 Go dans `backup/` (677 Go libres sur SSDBCK au
  2026-10-18 : OK, mais garde-fou à prévoir ?).
- ⬜ **Reprise** après échec : relancer repart de zéro (tout recompresser) — acceptable ?
- ⬜ Options de test : `--limit N` (limiter aux N premiers dossiers) et/ou `--dry-run`
  (tout calculer sans rien envoyer) ?

## 7. Configuration

- Les chemins machine sont portés par des **symlinks non versionnés** (`source/`, `backup/`),
  comme dans `autobackup` ⬜ (alternative : variables d'environnement).
- Destination Proton : `/my-files/databackup` (constante de projet, pas un secret).
- ⬜ **Mot de passe des zips : hors du code.** `autobackup` le garde en dur (dette connue,
  à ne pas reproduire). Emplacement à choisir : variable d'environnement, ou fichier local
  non versionné (`.env` / `config.local.*`, déjà couverts par `.gitignore`).
- ⬜ Le mot de passe doit aussi être **sauvegardé quelque part** (gestionnaire de mots de
  passe) : sans lui, les archives sont irrécupérables.

## 8. Exécution

- v1 **manuelle** : `./start.sh [compress|transfer|cleanup|all]` (défaut `all`), qui crée le
  venv si besoin puis exécute le script.
- ⬜ **Verrou anti-concurrence** : deux exécutions simultanées partageraient le même dossier
  `backup/` et se détruiraient mutuellement — verrou fichier nécessaire ?
- ⬜ Planification ultérieure (cron / timer systemd) et fréquence ? *(hors v1)*

## 9. Journalisation et restitution

- Un fichier de log **horodaté par exécution** dans `logs/`, rotation : les **7 derniers**.
- Avancement affiché **en direct** : étape et compteur `[n/total]`, dossier ou archive en
  cours, taille, durée écoulée.
- ⬜ **Récapitulatif final** : nombre d'archives, volume total, erreurs ?
- ⬜ Niveau de détail : les noms d'archives (= noms de dossiers) apparaissent-ils dans les
  logs ? (machine personnelle : a priori oui, cf. §11)

## 10. Restauration

- Les archives sont chiffrées en **AES-256** : elles s'ouvrent avec **7-Zip** (ou `pyzipper`).
- Procédure v1 (documentée, non outillée) :
  1. `./proton-drive filesystem download /my-files/databackup/<archive>.zip .`
  2. ouvrir l'archive avec le mot de passe du §4 ;
  3. extraire à l'emplacement voulu.
- ⬜ **Test de restauration réel** à prévoir (règle : une sauvegarde non testée n'est pas une
  sauvegarde).
- ⚠️ Les dossiers vides n'existent pas dans les archives : leur structure n'est pas restituée.

## 11. Sécurité et données personnelles

- `source/` ouvert en **lecture seule** : contrôle à prévoir (comparaison de la liste et des
  empreintes des fichiers avant/après une exécution).
- Aucun secret versionné : `proton-drive`, `.venv/`, `logs/`, `source`, `backup` et les
  fichiers de config locale sont dans `.gitignore`.
- ⬜ Mot de passe des zips : emplacement (cf. §7) et **sauvegarde** hors projet.
- ⬜ Les logs exposent-ils trop ? (noms de dossiers `Compta`, `Assurances`, `YM`…) — machine
  personnelle, dépôt privé : a priori acceptable, à confirmer.
- ⚠️ `auth login` est **interactif** (navigateur) : en cas d'expiration de session, un
  transfert non supervisé échouera.

## 12. Questions ouvertes

Décisions déjà prises avec Yves : racine `source` en lecture seule (§3) ; dossier temporaire
`backup` (§6) ; un zip par dossier de premier niveau + `documents.zip` (§3) ; chiffrement
AES-256 avec le mot de passe d'`autobackup` (§4) ; **écrasement** des fichiers existants sur
Proton (§5).

Restent à trancher :

1. **Nommage des archives** (espaces et caractères spéciaux conservés ? préfixe ?).
2. **Fichiers déjà compressés** stockés sans compression (`ZIP_STORED`) ou non.
3. **Dossiers vides** : ignorés (aucune archive) ou représentés ?
4. **Fichiers temporaires** (`.xhb~`) et **fichiers cachés** : inclus ou exclus ?
5. **Liens symboliques** rencontrés dans l'arborescence : suivis ou ignorés ?
6. **Archives orphelines** sur Proton : conservées (recommandé) ou supprimées ?
7. **Mot de passe zip hors du code** : variable d'environnement ou fichier local non versionné ?
8. **Verrou anti-concurrence** : nécessaire en v1 ?
9. **Options de test** : `--limit N` et/ou `--dry-run` ?
10. **Quota Proton** : contrôle avant transfert, et comportement si insuffisant ?
11. **Restauration** : documentée seulement (v1) ou commande outillée dès v1 ?
12. **Planification** automatique : prévue pour plus tard, ou jamais (exécution manuelle assumée) ?

## 13. Évolutions envisagées (hors v1)

- sauvegarde incrémentale avec historique daté (au lieu de l'écrasement) ;
- suppression des archives orphelines (miroir strict de l'état local) ;
- commande de restauration outillée (`./start.sh restore`) ;
- notification de fin (mail, notification bureau) ;
- autres sources : photos hors `source`, dépôts Git, bases de données ;
- contrôle d'intégrité périodique des archives distantes ;
- interface de suivi (dernières sauvegardes, volumétrie).

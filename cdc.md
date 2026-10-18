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
| Dossiers vides | **pas d'archive** pour un dossier de premier niveau vide ; **dans** une archive, les sous-dossiers vides sont **conservés** (arborescence fidèle). *(les 2 dossiers vides relevés sont imbriqués, aucun au premier niveau)* |
| Liens symboliques internes | **ignorés**, avec un **avertissement dans le log** (aucun suivi de lien : évite les boucles et les sorties de périmètre). *(la racine `source/` est elle-même un lien, résolu une fois ; aucun lien interne aujourd'hui)* |
| Fichiers temporaires | **inclus** : le script **ne filtre rien** (y compris `Compta Homebank.xhb~` et les `.bak` datés) |
| Fichiers cachés (`.…`) | **inclus** *(aucun aujourd'hui à la racine)* |
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
- Une archive par dossier de premier niveau ; **`documents.zip`** pour les fichiers de la racine.
- Écrasement côté Proton (miroir de l'état courant, cf. §5).
- **Aucun filtrage** : le script n'exclut ni temporaires, ni `.bak`, ni fichiers cachés (§3).

### Nommage normalisé

Le nom du dossier est **normalisé** pour produire le nom de l'archive :

1. accents supprimés (normalisation Unicode NFKD) ;
2. passage en **minuscules** ;
3. tout groupe de caractères hors `a-z0-9` remplacé par un **tiret** (tirets de bord retirés) ;
4. suffixe **`.zip`**.

Exemples actuels : `Skills et modèles IA` → `skills-et-modeles-ia.zip` · `Garanties - modes
d'emploi` → `garanties-modes-d-emploi.zip` · `Complotiste !` → `complotiste.zip` ·
`Places de camp` → `places-de-camp.zip`. Appliqué aux 21 dossiers actuels : **aucune
collision**. Les fichiers de la racine vont dans `documents.zip`.

- ⬜ **Collision** si deux dossiers normalisés donnaient le même nom : échec explicite du scan
  (recommandé — pas d'écrasement silencieux) ou suffixe numéroté ?
- ⬜ Un dossier nommé `Documents` produirait `documents.zip`, même nom que le zip des fichiers
  racine : même règle de collision à appliquer.

### Compression

- **ZIP_STORED** (aucune compression, mais **toujours chiffrés** AES-256) pour les formats
  déjà compressés : `jpg`, `jpeg`, `png`, `gif`, `mp4`, `stl`, `3mf`, `zip`. C'est l'essentiel
  du volume (≈ 4,2 Go sur 4,8 : `Photos` 3,2 Go de `jpg`, `Prusa` 628 Mo de `stl`/`3mf`) : le
  gain de compression y est négligeable, le coût CPU réel.
- **ZIP_DEFLATED** pour tout le reste (`pdf`, `odt`, `txt`, `f3d`, `dwg`, `sh`…).
- ⬜ Faut-il ajouter à la liste les formats **conteneurs zip** (`odt`, `ods`, `docx`, `pptx`,
  `xlsx`) ? Le gain y est faible mais ces fichiers sont petits.
- ⬜ Niveau de compression zip : laisser le défaut ?

## 5. Destination et transfert (Proton Drive)

**Décidé**

- Outil : CLI officiel **`proton-drive`**, installé par `./install.sh`, **non versionné**
  (référence : `usage-proton-drive-cli.md`).
- Destination : **`/my-files/databackup`**.
- Un appel `upload` **par archive** :
  `./proton-drive filesystem upload -f replace <archive> /my-files/databackup`
- **`-f replace` = les archives distantes de même nom sont écrasées** par la version locale
  (la version remplacée part dans la corbeille Proton : pas d'historique géré par nous).
- **Authentification hybride, mais jamais de `login` en aveugle** : ni `login` ni `logout`
  systématique. En cas d'échec d'un upload, la tentative d'`auth login` (navigateur,
  interactif) puis la reprise de l'upload n'ont lieu **que dans un terminal**. En exécution
  **sans TTY** (Piloter, cron), le script échoue avec le code retour `4` et le message
  « lancez `./proton-drive auth login` » (cf. §8).

- **Archives orphelines** (sur Proton, dont le dossier source n'a plus d'existence) :
  **conservées et ignorées** — **rien n'est jamais supprimé** côté distant en v1. Le dossier
  de destination peut donc contenir des archives d'anciens dossiers : à nettoyer à la main.
- **Quota : aucun contrôle automatique.** Le CLI n'expose pas l'espace libre du compte (il
  n'a que `filesystem size <path>`, la taille d'un dossier). Un dépassement se traduit par un
  **échec d'upload** : message clair, compté en échec, code retour `1`. Vérification manuelle
  recommandée dans l'interface web Proton avant la première grosse sauvegarde (≈ 4,8 Go).

**À trancher** (voir §12, lot C)

- ⬜ **Gros fichier** : `Photos.zip` ≈ 3,2 Go en un seul upload — à valider sur un transfert
  réel (durée, robustesse).
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
- **Mot de passe des archives : hors du code** *(décidé le 2026-10-18)*. `autobackup` le
  garde en dur (dette connue, à ne pas reproduire ici).
  - stockage : fichier **`.env` local non versionné** à la racine du projet (`chmod 600`,
    déjà couvert par `.gitignore`), lu par `start.sh` ;
  - la variable d'environnement **`DATABACKUP_ZIP_PASSWORD` est prioritaire** si elle est
    définie (Piloter peut l'injecter plus tard via le champ `env` de son bouton) ;
  - le mot de passe est **déjà conservé dans le gestionnaire de mots de passe de Yves** :
    sans lui, les 21 archives sont irrécupérables ;
  - ⚠️ il ne doit apparaître **ni dans le code, ni dans un log, ni dans la sortie** (cf. §11).

## 8. Exécution

- v1 **manuelle** : `./start.sh [scan|archive|transfer|cleanup|all]` (défaut `all`), qui crée le
  venv si besoin, installe les dépendances puis exécute le module Python.
  **Créé en I1** (décision du 2026-10-18 : pas de script non fonctionnel en dépôt avant I1).
- Étapes sélectionnables comme dans `autobackup` (`scan` / `archive` / `transfer` / `cleanup`
  séparés), pour pouvoir rejouer une étape sans tout recalculer.
- **Options de test** *(décidé le 2026-10-18)* : `--dry-run` — affiche le plan complet
  (dossiers retenus, noms d'archives normalisés, tailles estimées, cible) **sans rien écrire
  ni envoyer** ; `--limit N` — ne traiter que les **N premiers dossiers**, pour tester un
  transfert réel sans envoyer 4,8 Go. Les deux sont transmis au module par `start.sh`.
- ⬜ **Verrou** ⚠️ : deux exécutions simultanées partageraient le dossier `backup/` et se
  détruiraient mutuellement — décision ci-dessous.

### Contrat de `start.sh` — compatible Piloter

`start.sh` est le **lanceur unique** du projet : usage manuel **et** pilotage par
l'extension **Piloter** (même approche qu'`autobackup`).

**Décidé**

- **Exécutable**, lancé depuis n'importe quel dossier (`cd` sur le dossier du script),
  `set -euo pipefail` ; arguments transmis au module.
- **Fonctionne sans TTY** (Piloter l'appelle avec `</dev/null`) : aucun prompt, aucune
  attente clavier.
- **Code retour exploitable** : `0` = succès complet, non nul = échec (Piloter ne distingue
  que ces deux cas). Codes distincts pour l'usage manuel : `1` échec générique (archivage ou
  transfert), `2` argument invalide, `3` dossier `backup/` indisponible (disque non monté),
  `4` authentification Proton requise, `5` sauvegarde déjà en cours (verrou).
- **Verrou `.databackup.lock`** (PID) : un second lancement est **refusé** avec le code `5`
  et un message clair. Il sert aussi de **témoin d'activité** (base d'un futur statut Piloter
  « sauvegarde en cours ») et est retiré en fin de run, y compris après une annulation.
- **Annulable** : sur `SIGTERM` (timeout Piloter, clic sur la tuile « en cours »), arrêt
  propre — le processus `proton-drive` en cours est terminé, le verrou est libéré, le code
  retour est non nul. Aucun processus détaché ne doit survivre.
- **Sortie ligne par ligne sur la sortie standard** (le journal de Piloter en garde 500
  lignes) : étapes, compteur `[n/total]`, nom d'archive, taille, durée. **Jamais de secret**
  dans la sortie (cf. §11).
- `exec` du module Python pour conserver le **groupe de processus** créé par Piloter
  (indispensable pour que `timeout` et l'annulation atteignent réellement le traitement).

**Côté Piloter** (autre dépôt, à faire quand tu le demandes)

- Un **adaptateur** `piloter/scripts/databackup-start.sh` qui délègue par `exec` à ce
  `start.sh` (glue de convention seulement, comme `autobackup-start.sh`).
- Un bouton **déclencheur** « Sauvegarde docs » : `confirm: true`, `timeout` ⬜ (proposition :
  **2 h**, la sauvegarde envoyant ~4,8 Go — contre 1 h pour `autobackup`).
- Optionnel, plus tard : `piloter/scripts/databackup-status.sh` lisant `.databackup.lock`
  pour afficher « en cours ».
- ⬜ Planification ultérieure (cron / timer systemd) et fréquence ? *(hors v1)*
- ⬜ Si planifié un jour : gare au **verrou** et à l'**authentification** (§5) — un run
  automatique ne peut pas ouvrir de navigateur.

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
- **Mot de passe des zips** : `.env` local non versionné (priorité à `DATABACKUP_ZIP_PASSWORD`),
  jamais dans le code, les logs ou la sortie d'exécution (cf. §7) ; conservé dans le
  gestionnaire de mots de passe de Yves.
- ⬜ Les logs exposent-ils trop ? (noms de dossiers `Compta`, `Assurances`, `YM`…) — machine
  personnelle, dépôt privé : a priori acceptable, à confirmer.
- ⚠️ `auth login` est **interactif** (navigateur) : en cas d'expiration de session, un
  transfert non supervisé échouera.

## 12. Questions ouvertes

**Déjà tranché**

- *Socle* : racine `source` en **lecture seule** (§3) ; dossier temporaire `backup` (§6) ; un
  zip par dossier de premier niveau + `documents.zip` (§3) ; chiffrement **AES-256** avec le
  mot de passe d'`autobackup` (§4) ; **écrasement** des fichiers existants sur Proton (§5).
- *Lot A — contenu des archives (2026-10-18)* : **nommage normalisé** (§4) ; `ZIP_STORED`
  pour `jpg/jpeg/png/gif/mp4/stl/3mf/zip` ; **pas d'archive** pour un dossier de premier
  niveau vide (sous-dossiers vides conservés dans les archives) ; **aucun filtrage**
  (temporaires, `.bak`, `*~`, fichiers cachés inclus) ; liens symboliques **ignorés avec
  avertissement** ; `documents.zip` pour les fichiers de la racine.
- *Exécution et Piloter (2026-10-18)* : `start.sh` = **lanceur unique**, conforme au contrat
  Piloter (sans TTY, codes retour, sortie ligne à ligne, annulable) et **créé en I1** (§8) ;
  **verrou `.databackup.lock`** dès la v1 ; **pas de `auth login` sans TTY** → échec avec le
  code `4` (§5, §8).
- *Lot B — transfert et secret (2026-10-18)* : archives **orphelines conservées** et ignorées
  (rien n'est supprimé côté Proton) ; **aucun contrôle de quota** (le CLI ne l'expose pas, un
  dépassement fait échouer l'upload) ; mot de passe dans **`.env` local non versionné**
  (priorité à `DATABACKUP_ZIP_PASSWORD`), **déjà sauvegardé** dans le gestionnaire de Yves ;
  options **`--dry-run`** et **`--limit N`** (§8).

**Lot C — archive et restitution**

1. **Collision** de noms normalisés (§4) : échec explicite (recommandé) ou suffixe numéroté ?
2. **Liste `ZIP_STORED`** : ajouter les formats conteneurs zip (`odt`, `ods`, `docx`…) ? Et le
   niveau de compression zip (défaut ?) ?
3. **Reprise après échec** : relancer repart de zéro (tout recompresser) — acceptable ? Et en
   cas de **coupure réseau** au milieu d'un upload (§5) ?
4. **Vérification post-transfert** : comparer la taille, l'empreinte, ou rien ?
5. **Fichiers modifiés pendant l'exécution** : `source` est synchronisée par kDrive — avertir
   et continuer, ou échouer ?
6. **Gros fichier** : valider en réel le transfert de `Photos.zip` (≈ 3,2 Go) — durée,
   robustesse, et ajustement du `timeout` Piloter en conséquence (§8).
7. **Restauration** : documentée seulement (v1) ou commande outillée dès v1 ?
8. **Planification** automatique : plus tard, ou jamais (exécution manuelle assumée) ?
9. **Logs** : les noms de dossiers (donc de `Compta`, `Assurances`, `YM`…) restent-ils tels
   quels dans les logs ? (§11)

## 13. Évolutions envisagées (hors v1)

- sauvegarde incrémentale avec historique daté (au lieu de l'écrasement) ;
- suppression des archives orphelines (miroir strict de l'état local) ;
- commande de restauration outillée (`./start.sh restore`) ;
- notification de fin (mail, notification bureau) ;
- autres sources : photos hors `source`, dépôts Git, bases de données ;
- contrôle d'intégrité périodique des archives distantes ;
- interface de suivi (dernières sauvegardes, volumétrie).

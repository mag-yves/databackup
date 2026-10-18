# Cahier des charges — DataBackup

> **Source de vérité du projet.** Toute évolution fonctionnelle est écrite et validée ici
> **avant** d'être codée. Les décisions actées sont en gras dans les sections concernées et
> récapitulées au §12 ; les rares ⬜ qui subsistent sont des **vérifications à faire en réel**,
> pas des questions ouvertes.
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
- **suppression** côté Proton (les archives orphelines sont conservées, cf. §5) ;
- **restauration** : aucune procédure ni outil en v1 (reportée après la v1, cf. §10) ;
- **planification automatique** : décision **définitive** — cron / timer systemd sont exclus,
  la sauvegarde est toujours déclenchée à la main (§8) ;
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
| Liens symboliques internes | **ignorés**, avec un **avertissement dans le log** (aucun suivi de lien : évite les boucles et les sorties de périmètre). *(la racine `source/` est elle-même un lien, résolu une fois ; **1 lien interne relevé le 2026-10-18** dans `Prusa/Modèles/02 en cours/Zetests` — ignoré et signalé)* |
| Fichiers temporaires | **inclus** : le script **ne filtre rien** (y compris `Compta Homebank.xhb~` et les `.bak` datés) |
| Fichiers cachés (`.…`) | **inclus** *(aucun aujourd'hui à la racine)* |
| Fichiers modifiés pendant l'exécution | **avertir et continuer** : le zip contient la version lue au moment de l'archivage ; un fichier disparu ou illisible est **signalé dans le log** et n'interrompt pas le dossier (il sera repris au run suivant) |

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

- **Collision = échec du scan** *(décidé le 2026-10-18)* : si deux dossiers se normalisent vers
  le même nom, ou si un dossier produisait `documents.zip` (un dossier nommé `Documents`), le
  scan **s'arrête** avec un message nommant les dossiers en conflit — jamais d'écrasement
  silencieux côté Proton.

### Compression

- **ZIP_STORED** (aucune compression, mais **toujours chiffrés** AES-256) pour les formats
  déjà compressés : `jpg`, `jpeg`, `png`, `gif`, `mp4`, `stl`, `3mf`, `zip`. C'est l'essentiel
  du volume (≈ 4,2 Go sur 4,8 : `Photos` 3,2 Go de `jpg`, `Prusa` 628 Mo de `stl`/`3mf`) : le
  gain de compression y est négligeable, le coût CPU réel.
- **ZIP_DEFLATED** pour tout le reste (`pdf`, `odt`, `txt`, `f3d`, `dwg`, `sh`…).
- **Liste figée** *(décidé le 2026-10-18)* : elle reste celle ci-dessus. Les formats conteneurs
  zip (`odt`, `ods`, `docx`, `pptx`, `xlsx`) sont **compressés normalement** : fichiers petits,
  aucun enjeu, pas de règle supplémentaire à maintenir.
- **Niveau de compression** : celui **par défaut** de la bibliothèque pour les fichiers
  compressés.

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
  *(relevé le 2026-10-18 : `filesystem size` **compte aussi les éléments en corbeille** — après
  un run qui écrase des archives (`-f replace`), il **surestime** du volume remplacé ; ne pas
  le confondre avec l'espace réellement occupé.)*

**Échecs et validation** *(décidé le 2026-10-18 — détail au §6)*

- **Coupure réseau** en cours de transfert : l'archive est **comptée en échec** et le run
  **continue** ; on relance à la main plus tard (tout est alors recompressé, §6).
- **Aucune vérification post-transfert** : le code retour de `proton-drive` fait foi.
- ✅ **Gros fichier** *(mesuré le 2026-10-18)* : `photos.zip` (3,19 Go) envoyé en **9:01** en un
  seul upload ; **run complet : 14:25** pour 22 archives (4,63 Go) — bien en deçà du `timeout`
  Piloter de 1 h, **aucun ajustement nécessaire** (cf. §8).

## 6. Processus (déroulé d'une exécution)

1. **Contrôle** — le disque de `backup/` est monté et accessible en écriture, sinon échec
   explicite (`backup/` → `/media/yves/SSDBCK/temp/backup`).
2. **Nettoyage** — `backup/` est **vidé** avant toute chose (il est temporaire).
3. **Scan** — dossiers de premier niveau de `source/` retenus + fichiers racine ; les
   dossiers vides sont écartés ; toute **collision de noms d'archives** arrête le scan (§4).
4. **Archives** — création des zips chiffrés dans `backup/`.
5. **Transfert** — envoi des zips de `backup/` vers `/my-files/databackup`, un `upload` par
   zip.
6. **Nettoyage final** — `backup/` est vidé **quoi qu'il arrive** (détail ci-dessous).

### Nettoyage du dossier temporaire `backup/` *(règle ferme, confirmée le 2026-10-18)*

`backup/` est **temporaire par nature** : il ne doit **jamais** rester des archives dedans
après un traitement. Garanties attendues :

- **vidé au début** de chaque run (étape 2) : c'est ce qui rattrape un run interrompu
  brutalement (coupure de courant, `kill -9`, plantage) — le résidu ne pollue pas le run
  suivant ;
- **vidé à la fin d'un run `all`**, dans **tous** les cas :
  - succès complet,
  - **échec** d'archivage ou de transfert (le run se termine en `1`) ;
  - **annulation** par `SIGTERM` / `SIGINT` (timeout Piloter, `Ctrl-C`, clic sur la tuile) ;
- **vidé par l'étape `cleanup`** appelée seule ;
- **exception voulue** : `scan` et `archive` **seuls** laissent volontairement les archives
  dans `backup/` — c'est le principe même de l'étape (compresser d'abord, transférer ensuite
  avec `transfer`). Le vidage n'intervient que sur `cleanup` ou en fin de `all` ;
- si le vidage est impossible (disque démonté pendant le run), le run **échoue** avec un
  message explicite (`3`) et **rien d'autre n'est supprimé** — on ne touche jamais à
  `source/` ni à Proton ;
- **`SIGKILL`** (inatteignable proprement) : aucune garantie possible, c'est le vidage du
  début du run suivant qui nettoie.

Conséquence **assumée et confirmée par Yves** (2026-10-18) : sur un run complet, **les
archives ne survivent pas** à l'exécution, même celles dont le transfert a échoué (aucune
copie locale conservée, aucune exception « garder pour diagnostic » — piste examinée puis
écartée). La copie de référence est celle de **Proton Drive**, et le run suivant recompresse
tout : c'est le prix de la simplicité (aucun état persisté, cf. « Relancer repart de zéro »).

### Gestion des échecs *(décidé le 2026-10-18)*

- Un `upload` en échec (coupure réseau, quota, session Proton expirée) est **compté en échec
  et le run continue** avec les archives suivantes ; le récapitulatif final les liste et le
  code retour est `1` (§8). Aucun réessai automatique.
- **Aucune vérification supplémentaire** après transfert : le **code retour** de
  `proton-drive` fait foi (pas d'appel `filesystem size`, pas de comparaison d'empreinte).
- Un fichier qui **disparaît ou devient illisible** pendant l'archivage → **avertissement
  dans le log et on continue** (il sera repris au run suivant) ; le dossier n'échoue pas.
- Une **date de modification hors plage ZIP** (avant 1980 ou après 2107) : le fichier est
  **archivé quand même, avec la date ramenée à 1980**, avec un avertissement — mieux vaut une
  date approximative que perdre le fichier. *(2 fichiers datés 1979 relevés le 2026-10-18 dans
  `Prusa` : cause d'un échec réel corrigé en I5.)*
- Un fichier que le format **refuse d'ajouter** (nom non encodable…) → **avertissement et
  fichier ignoré**, sans interrompre l'archive ni le dossier.
- **Relancer repart de zéro** : tout est recompressé (aucun état persisté entre deux
  exécutions). Accepté en v1 — le coût est la lecture de ~4,8 Go.
- Espace disque : jusqu'à ~4,8 Go dans `backup/` (677 Go libres sur SSDBCK au 2026-10-18) —
  aucun garde-fou dédié, l'échec d'écriture restant un échec explicite.

✅ **Première validation réelle** (2026-10-18) : run complet en **14:25** — 22 archives créées
(4,63 Go), 22 envoyées, **0 échec**, `backup/` vidé, code retour `0` (dont `photos.zip`
= 3,19 Go, 9:01).

## 7. Configuration

- Les chemins machine sont portés par des **symlinks non versionnés** (`source/`, `backup/`),
  comme dans `autobackup` — décision conservée : ils fonctionnent et restent propres à la
  machine (les alternatives par variables d'environnement n'apportent rien ici).
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
- **Annulable** : sur `SIGTERM` / `SIGINT` (timeout Piloter, clic sur la tuile « en cours »,
  `Ctrl-C`), arrêt propre — le processus `proton-drive` en cours est terminé, le dossier
  `backup/` est **vidé** (comme en fin de run normal, cf. §6), le verrou est libéré, le code
  retour est non nul. Aucun processus détaché ne doit survivre.
- **Sortie ligne par ligne sur la sortie standard** (le journal de Piloter en garde 500
  lignes) : étapes, compteur `[n/total]`, nom d'archive, taille, durée. **Jamais de secret**
  dans la sortie (cf. §11).
- `exec` du module Python pour conserver le **groupe de processus** créé par Piloter
  (indispensable pour que `timeout` et l'annulation atteignent réellement le traitement).

**Côté Piloter** (autre dépôt, à faire quand tu le demandes)

- Un **adaptateur** `piloter/scripts/databackup-start.sh` qui délègue par `exec` à ce
  `start.sh` (glue de convention seulement, comme `autobackup-start.sh`).
- Un bouton **déclencheur** « Sauvegarde docs » : `confirm: true`, **`timeout: 3600` (1 h)**
  *(décidé le 2026-10-18, comme `autobackup`)*. ✅ **Confirmé par la mesure du 2026-10-18** :
  run complet à froid en **14:25** (≈ 4,8 Go) — le timeout de 1 h laisse une large marge,
  **aucun ajustement nécessaire**. Un run coupé par le `timeout` n'est pas perdu : arrêt propre,
  verrou libéré, `backup/` vidé, il suffit de relancer.
- Optionnel, plus tard : `piloter/scripts/databackup-status.sh` lisant `.databackup.lock`
  pour afficher « en cours ».
- **Aucune planification** *(décision définitive du 2026-10-18)* : ni cron, ni timer systemd.
  Le déclenchement est **toujours manuel** (bouton Piloter ou `./start.sh`) — l'authentification
  Proton (§5) et le verrou restent ainsi sous contrôle humain, et un run ne tombe jamais quand
  le portable est fermé.

## 9. Journalisation et restitution

- Un fichier de log **horodaté par exécution** dans `logs/`, rotation : les **7 derniers**.
- Avancement affiché **en direct** : étape et compteur `[n/total]`, dossier ou archive en
  cours, taille, durée écoulée.
- **Récapitulatif final** *(décidé le 2026-10-18)* : nombre d'archives, volume total, durée et
  échecs — affiché et journalisé à la fin du run (livrable d'I5).
- **Noms d'archives visibles** dans le log et le terminal, pour rendre le diagnostic possible
  (cf. §11).

## 10. Restauration

**Hors v1** *(décidé le 2026-10-18)* : la v1 ne livre **ni procédure ni outil** de
restauration. Les archives sont des **zip AES-256 standard**, ouvrables avec **7-Zip** (ou
`pyzipper`) avec le mot de passe du §4 : la restitution reste possible à tout moment, mais
elle sera documentée et testée après la v1 (§13).

⚠️ **Risque assumé** : la restitution **depuis Proton Drive** n'aura pas été testée avant la
fin de la v1. Mitigation partielle : les tests d'I3 ouvrent les archives produites localement
et en vérifient le contenu et le chiffrement — cela couvre le risque de **format**, pas celui
du **téléchargement**.

⚠️ Un **dossier de premier niveau vide** ne produit pas d'archive : sa structure n'est pas
restituée. En revanche, les **sous-dossiers vides** d'un dossier sauvegardé sont conservés
dans l'archive (§3).

Pour mémoire, la procédure à écrire puis tester :

    ./proton-drive filesystem download /my-files/databackup/<archive>.zip .
    # puis ouvrir l'archive avec le mot de passe du §4 et extraire à l'emplacement voulu

## 11. Sécurité et données personnelles

- `source/` ouvert en **lecture seule** : contrôle à prévoir (comparaison de la liste et des
  empreintes des fichiers avant/après une exécution).
- Aucun secret versionné : `proton-drive`, `.venv/`, `logs/`, `source`, `backup` et les
  fichiers de config locale sont dans `.gitignore`.
- **Mot de passe des zips** : `.env` local non versionné (priorité à `DATABACKUP_ZIP_PASSWORD`),
  jamais dans le code, les logs ou la sortie d'exécution (cf. §7) ; conservé dans le
  gestionnaire de mots de passe de Yves.
- **Exception assumée** *(décidée le 2026-10-18)* : le mot de passe figure **en clair au §4** du
  présent CDC. Dépôt **privé**, script **déclenché uniquement en local** dans la session de
  Yves. La règle « jamais dans le **code**, les **logs** ni la **sortie d'exécution** » reste
  entière : seul le document versionné fait exception.
- **Noms de dossiers et d'archives visibles** dans le log et dans le terminal *(décidé le
  2026-10-18)* : c'est ce qui rend le diagnostic possible (`[7/22] photos.zip — 3,2 Go —
  4:12`). Machine personnelle, dépôt privé, `logs/` non versionné — acceptable.
- ⚠️ `auth login` est **interactif** (navigateur) : en cas d'expiration de session, un
  transfert non supervisé échouera.

## 12. Décisions — récapitulatif

> **Le CDC v1 est figé** : toutes les questions des trois lots ont été tranchées avec Yves le
> **2026-10-18**. Cette section n'est plus une liste de questions, mais l'index des décisions
> (le détail vit dans les sections concernées). Toute évolution passe par le §13 ou une
> nouvelle décision écrite ici.

**Socle**

- `source/` en **lecture seule absolue**, dossier temporaire `backup/` (§3, §6) : **vidé au
  début et à la fin de chaque run** — succès, échec ou annulation — sauf `scan`/`archive`
  lancés seuls, qui le laissent volontairement en place pour un `transfer` ultérieur.
- **Un zip par dossier de premier niveau** + **`documents.zip`** pour les fichiers racine (§3).
- Chiffrement **AES-256**, mot de passe du §4 ; **écrasement** des archives distantes (§5).

**Lot A — contenu des archives**

- **Nommage normalisé** des archives (§4) ; **collision = échec du scan**.
- `ZIP_STORED` pour `jpg jpeg png gif mp4 stl 3mf zip` (liste figée, niveau de compression par
  défaut) ; `odt/ods/docx…` compressés normalement.
- **Pas d'archive** pour un dossier de premier niveau vide ; sous-dossiers vides conservés.
- **Aucun filtrage** : temporaires, `.bak`, `*~`, fichiers cachés inclus.
- Liens symboliques **ignorés avec avertissement**.

**Lot B — transfert et secret**

- Archives **orphelines conservées** (rien n'est jamais supprimé côté Proton) (§5).
- **Aucun contrôle de quota** — le CLI ne l'expose pas ; un dépassement fait échouer l'upload.
- Mot de passe dans **`.env` local non versionné** (priorité à `DATABACKUP_ZIP_PASSWORD`), déjà
  conservé dans le gestionnaire de mots de passe de Yves ; jamais dans le code ni les logs
  (§7, §11).
- Options **`--dry-run`** et **`--limit N`** (§8).

**Lot C — archive, échecs et restitution**

- Un upload en échec est **compté en échec et le run continue** ; **aucun réessai automatique**
  (§6). **Aucune vérification post-transfert** : le code retour du CLI fait foi.
- **Relancer repart de zéro** (aucun état persisté) — accepté en v1.
- Fichier **disparu ou illisible** pendant l'archivage : **avertir et continuer** (§6).
- **Restauration hors v1** (§10) : risque assumé (format validé localement en I3, pas le
  téléchargement), procédure à écrire et tester ensuite.
- **Aucune planification** : décision **définitive** (ni cron ni timer systemd) (§2, §8).
- **Noms de dossiers et d'archives visibles** dans le log et le terminal (§11).
- `timeout` du bouton Piloter : **1 h**, **confirmé** par le run réel du 2026-10-18 (14:25) ;
  premier run lancé **à la main**, aucun ajustement nécessaire (§8).

**Vérifications réelles : faites** (2026-10-18) — ✅ premier run réel complet : **14:25** pour
22 archives (4,63 Go), `photos.zip` (3,19 Go) en 9:01, **0 échec**, `backup/` vidé ; `timeout`
Piloter de **1 h confirmé** (§5, §6, §8). Le CDC v1 est désormais **intégralement vérifié**.

## 13. Évolutions envisagées (hors v1)

- **restauration** : procédure (téléchargement depuis Proton, déchiffrement, extraction),
  **test réel** associé, puis éventuelle commande outillée `./start.sh restore` (§10) ;
- sauvegarde incrémentale avec historique daté (au lieu de l'écrasement) ;
- suppression des archives orphelines (miroir strict de l'état local) ;
- notification de fin (mail, notification bureau) ;
- autres sources : photos hors `source`, dépôts Git, bases de données ;
- contrôle d'intégrité périodique des archives distantes ;
- interface de suivi (dernières sauvegardes, volumétrie).

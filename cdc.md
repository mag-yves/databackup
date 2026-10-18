# Cahier des charges — DataBackup

> **Source de vérité du projet.** Toute évolution fonctionnelle est écrite et validée ici
> **avant** d'être codée. Les sections marquées ⬜ sont à compléter avec Yves ; les questions
> ouvertes sont regroupées au §12 (liste vivante).
> Règles de travail : `AGENTS.md` — itérations prévues : `TODO.md`.

## 1. Objectif

Sauvegarder mes **documents**, **dossier par dossier**, et les envoyer vers **Proton Drive**.

⬜ Formulation complète du besoin en une phrase : quel problème est résolu ? (perte d'un
disque, sauvegarde hors site, historique des versions, partage…)

## 2. Périmètre

### Dans le périmètre (v1)

⬜ À compléter — hypothèse de départ : sauvegarde de tout ou partie de `~/Documents`,
granularité au dossier, transfert vers un dossier unique sur Proton Drive.

### Hors périmètre (v1)

⬜ À compléter — pistes pressenties : photos/vidéos, sauvegardes système, autres clouds,
synchronisation bidirectionnelle, restauration automatique.

## 3. Sources — quels dossiers ?

| Élément | Décision |
|---|---|
| Racine des documents | ⬜ (ex. `~/Documents`, un chemin sur SSD4TO…) |
| Granularité : l'unité sauvegardée | ⬜ (un sous-dossier de la racine = une archive ? quelle profondeur ?) |
| Sous-dossiers exclus | ⬜ (ex. `.git`, `node_modules`, caches, dossiers de synchronisation) |
| Fichiers ignorés | ⬜ (taille maximale, extensions, fichiers temporaires `~$…`, `*.tmp`) |
| Dossiers vides | ⬜ (ignorés, comme dans `autobackup` ?) |
| Liens symboliques | ⬜ (suivis, ignorés, ou traités comme des fichiers ?) |
| Fichiers verrouillés / modifiés pendant le run | ⬜ (avertir et continuer ? échouer ?) |

## 4. Format des archives

⬜ Décision à prendre. Options, avec l'expérience d'`autobackup` :

| Option | Avantage | Inconvénient |
|---|---|---|
| Zip **chiffré AES-256** (`pyzipper`) | confidentiel même si le compte cloud fuite | mot de passe à gérer ; pas de déduplication |
| Zip simple (non chiffré) | simple, diagnostic facile | lisible par quiconque accède au cloud |
| Copie brute des fichiers (1 fichier = 1 objet distant) | restauration simple, incrémental naturel | beaucoup plus d'objets à transférer |

⬜ Nommage des archives : miroir du chemin (`<niveau>-<sous-dossier>.zip`) ou préfixe daté ?
⬜ Incrémental / historique : conserve-t-on un seul état courant (miroir) ou des versions
datées ? (le miroir `-f replace` d'`autobackup` ne garde **pas** d'historique)
⬜ Que faire d'une archive absente en local mais présente sur Proton (orpheline) ?

## 5. Destination et transfert (Proton Drive)

**Décidé**

- Outil : CLI officiel `proton-drive`, installé par `./install.sh`, **non versionné** ;
  référence de fonctionnement : `usage-proton-drive-cli.md`.
- Destination : **`/my-files/databackup`** (créé au besoin).
- Un appel `upload` **par archive** (pas d'upload groupé) :
  `./proton-drive filesystem upload -f replace <archive> /my-files/databackup`
- **Authentification hybride** : ni `login` ni `logout` systématique ; en cas d'échec d'un
  upload, tentative d'`auth login` (navigateur, interactif) puis reprise de l'upload.
- Les archives présentes sur Proton mais absentes en local sont **ignorées** : rien n'est
  supprimé côté distant en v1.

**À trancher**

- ⬜ Quota Proton : contrôler l'espace disponible avant de lancer un transfert ?
- ⬜ Coupure réseau en cours de transfert : reprise, marquage, ou échec complet ?
- ⬜ Nommage côté distant identique au nom local, ou convention dédiée ?
- ⬜ Vérification post-transfert (taille et/ou empreinte comparées) ?

## 6. Processus (déroulé d'une exécution)

Étapes envisagées, sur le modèle d'`autobackup` (à valider) :

1. **scan** — parcours des sources, liste des dossiers retenus (mode `--dry-run`).
2. **archive** — création des archives dans un dossier **temporaire** local.
3. **transfer** — envoi des archives vers Proton Drive.
4. **cleanup** — vidage du dossier temporaire, **quoi qu'il arrive**.

⬜ Emplacement du dossier temporaire (disque local ou SSD externe type SSDBCK ?) : le volume
des archives peut être important.
⬜ Garde-fou d'espace disque avant l'archivage.
⬜ Reprise après échec : peut-on relancer sans tout recalculer ?
⬜ Option `--limit N` (comme `autobackup`) pour tester sur quelques dossiers ?

## 7. Configuration

⬜ Où vit la configuration : racine(s) source, destination, exclusions, stratégie de conflit ?
⬜ Format : fichier non versionné (`config.local.toml`/`.json`) ou variables d'environnement ?
⬜ **Aucun secret en clair** : mot de passe d'archive et identifiants hors du dépôt.
   (Dette connue d'`autobackup` : mot de passe en dur dans le code — à ne pas reproduire.)

## 8. Exécution

- v1 : **manuelle**, via `./start.sh` (à créer).
- ⬜ Au-delà : planification (cron / timer systemd) et fréquence souhaitée ?
- ⬜ Un lancement concurrent (deux exécutions en parallèle) est-il possible / interdit ?

## 9. Journalisation et restitution

- un fichier de log horodaté par exécution dans `logs/` ;
- rotation : ne conserver que les N derniers (proposition : 7, comme `autobackup`) ;
- avancement affiché **en direct** dans le terminal : étape et compteur `[n/total]`, dossier
  ou archive en cours, taille, durée.
- ⬜ Faut-il un récapitulatif final (nombre d'archives, volume, échecs) ?
- ⬜ Niveau de détail : les noms de fichiers vont-ils dans le log ? (cf. §11)

## 10. Restauration

⬜ Rédiger la procédure : télécharger une archive depuis Proton Drive, la déchiffrer si
besoin, la décompresser à l'emplacement voulu.
⬜ Prévoir un **test de restauration** réel (règle : une sauvegarde non testée n'est pas une
sauvegarde).
⬜ Restauration partielle (un seul fichier dans une archive) : supportée par l'outil ?

## 11. Sécurité et données personnelles

- Sources ouvertes en **lecture seule** : aucun document modifié, déplacé ou supprimé.
- Aucun secret versionné (`proton-drive`, `.venv/`, `logs/`, config locale → `.gitignore`).
- ⬜ Noms de fichiers et chemins dans les logs : acceptables (machine personnelle) ou à masquer ?
- ⬜ Mot de passe d'archive : où le stocker, comment le sauvegarder, qui d'autre y a accès ?

## 12. Questions ouvertes / décisions à prendre

1. ⬜ Quelle racine exacte pour les documents, et qu'est-ce qu'« un dossier » à sauvegarder
   (premier niveau sous la racine ? profondeur arbitraire ?) ?
2. ⬜ Les archives doivent-elles être **chiffrées** (AES-256 comme `autobackup`) ou non ?
3. ⬜ Souhaite-t-on un **historique daté** côté distant, ou un simple miroir de l'état courant ?
4. ⬜ Un **incrémental** (n'envoyer que ce qui a changé) est-il un besoin v1 ou une évolution ?
5. ⬜ Où placer le dossier temporaire, et quel volume faut-il prévoir ?
6. ⬜ Souhaite-t-on des exclusions par défaut (`.git`, `node_modules`, corbeilles locales,
   dossiers de travail temporaires) ?
7. ⬜ Restauration : doit-elle être outillée (`./start.sh restore`) ou seulement documentée ?
8. ⬜ Faut-il une planification automatique, et à quelle fréquence ?

## 13. Évolutions envisagées (hors v1)

- sauvegarde incrémentale avec historique daté ;
- notification de fin (mail, notification bureau) ;
- commande de restauration outillée ;
- autres sources (photos, dépôts Git, bases de données) ;
- contrôle d'intégrité périodique des archives distantes ;
- interface de suivi (tableau des dernières sauvegardes).

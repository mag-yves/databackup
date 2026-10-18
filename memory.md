# Mémoire de projet — DataBackup

> État **courant** et **prochaines actions**, à lire en début de session et à mettre à jour
> après tout changement significatif. Les règles de travail, la structure et les pièges sont
> dans `AGENTS.md` ; le détail fonctionnel vit dans `cdc.md`. **Ne rien dupliquer ici.**
> Plafond : ~40 lignes / 2 Ko.

## État courant

- Projet **initialisé** le 2026-10-18 : structure documentaire, suivi du temps (`devtime`),
  `install.sh` et `usage-proton-drive-cli.md` repris du projet de référence `autobackup`.
  **Aucune ligne de code applicatif** pour l'instant.
- Phase : **analyse** — `cdc.md` contient la structure d'analyse ; les sections ⬜ et les
  questions ouvertes (§12) sont à compléter avec Yves.
- Dépôt Git : `git@github.com:mag-yves/databackup.git` (déjà créé, vide), branche `main`.

## Décisions actées

- Besoin : sauvegarder mes **documents par dossier** et les envoyer vers **Proton Drive**,
  en réutilisant l'approche d'`autobackup` (CLI `proton-drive`, pas de synchronisation
  bidirectionnelle).
- Destination Proton : **`/my-files/databackup`** (à créer si absent).
- Binaire `proton-drive` téléchargé **dans le projet** par `./install.sh`, non versionné.
- Itérations prévues : `TODO.md` — I1 socle technique → I6 restauration, I0 = analyse/CDC.

## Dette / points d'attention

- Aucune dette technique (pas de code). Dette **à ne pas hériter** d'`autobackup` : mot de
  passe d'archive en dur dans le code.

## Prochaines actions

- 🔴 Compléter `cdc.md` : racine des documents, granularité (l'unité sauvegardée),
  exclusions, format des archives (zip chiffré ou non).
- 🔴 Trancher les questions ouvertes du `cdc.md` §12.
- 🟠 Démarrer I1 (socle technique) une fois le CDC v1 figé.

#!/usr/bin/env bash
# Lanceur unique DataBackup — usage manuel et pilotage par Piloter (cf. cdc.md §8).
#
# Crée l'environnement virtuel si besoin, installe les dépendances, puis exécute le
# module Python en transmettant les arguments.
#
# Contrat (cf. cdc.md §8) : sans TTY (aucun prompt), codes retour exploitables
# (0 succès, 1 échec, 2 argument invalide, 3 backup/ indisponible, 4 auth Proton
# requise, 5 sauvegarde déjà en cours), sortie ligne à ligne sur la sortie standard,
# annulable (SIGTERM / SIGINT).
#
# `exec` conserve le **groupe de processus** créé par Piloter (setsid) — indispensable
# pour que le `timeout` et l'annulation atteignent réellement le traitement. Le verrou
# et la gestion des signaux vivent donc dans le module Python (rien ne s'exécuterait
# dans ce shell après `exec`).
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

VENV=".venv"

if [ ! -x "$VENV/bin/python" ]; then
    echo "Création de l'environnement virtuel ($VENV)..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --upgrade pip
    "$VENV/bin/pip" install -r requirements.txt
fi

exec "$VENV/bin/python" databackup.py "$@"

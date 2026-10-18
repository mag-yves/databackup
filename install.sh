#!/usr/bin/env bash
# Télécharge le binaire proton-drive dans le dossier du projet.
# Usage : ./install.sh [--force]
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

VERSION="${PROTON_DRIVE_VERSION:-0.9.0}"
URL="https://proton.me/download/drive/cli/${VERSION}/linux-x64/proton-drive"
DEST="proton-drive"

force=0
if [ "${1:-}" = "--force" ]; then
    force=1
fi

if [ -x "$DEST" ] && [ "$force" -ne 1 ]; then
    echo "$DEST déjà présent (utilise --force pour retélécharger)."
    exit 0
fi

if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 -o "$DEST" "$URL"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$DEST" "$URL"
else
    echo "Erreur : curl ou wget requis." >&2
    exit 1
fi

chmod +x "$DEST"

# Vérifie qu'on a bien un exécutable ELF (et non une page d'erreur HTML).
if [ ! -s "$DEST" ] || [ "$(head -c 4 "$DEST")" != "$(printf '\x7fELF')" ]; then
    echo "Erreur : le fichier téléchargé n'est pas un exécutable valide." >&2
    rm -f "$DEST"
    exit 1
fi

echo "proton-drive $VERSION installé dans $(pwd)/$DEST."
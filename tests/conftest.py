"""Isolation commune aux tests — cf. ``TODO.md`` I7.

``.databackup-state.json`` (historique de la sauvegarde incrémentale, cf. ``cdc.md`` §6) vit à
la **racine du projet** : sans précaution, un test qui appelle ``plan_archives`` sur une
arborescence factice lirait l'historique réel de la machine et pourrait ignorer des dossiers
factices parce qu'ils porteraient le nom d'une archive déjà sauvegardée. On redirige donc
systématiquement l'état vers le dossier temporaire du test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import databackup


@pytest.fixture(autouse=True)
def isolated_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirige l'historique vers ``tmp_path`` : aucun test ne touche l'état réel."""
    state = tmp_path / ".databackup-state.json"
    monkeypatch.setattr(databackup, "STATE_FILE", state)
    return state

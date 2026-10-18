"""Tests de l'étape « transfert » (I4) — cf. ``TODO.md``.

Utilise une **doublure** de ``proton-drive`` (petit script Python) : succès, échec compté sans
interruption, reprise après ``auth login`` en terminal, échec hors terminal (code `4`), binaire
absent, absence d'archive et ``--dry-run``. Aucun réseau, aucun vrai Proton.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import databackup

# Doublure : journalise ses appels, échoue/« se connecte » selon des fichiers témoins.
FAKE_PROTON = '''#!/usr/bin/env python3
"""Doublure de proton-drive (tests DataBackup) — ne contacte aucun réseau."""
import os
import sys
from pathlib import Path

state = Path(os.environ["FAKE_STATE"])
with (state / "calls.log").open("a", encoding="utf-8") as handle:
    handle.write(" ".join(sys.argv[1:]) + "\\n")

args = sys.argv[1:]
if args[:2] == ["auth", "login"]:
    sys.exit(0 if (state / "login_ok").exists() else 1)

if args[:2] == ["filesystem", "upload"]:
    if (state / "fail_always").exists() or (state / "fail_once").exists():
        (state / "fail_once").unlink(missing_ok=True)
        print("upload refuse (simulation)", file=sys.stderr)
        sys.exit(1)
    (state / "uploaded").mkdir(exist_ok=True)
    (state / "uploaded" / Path(args[-2]).name).touch()
    print("upload ok (simulation)")
    sys.exit(0)

sys.exit(2)
'''


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Projet isolé + doublure de ``proton-drive`` + terminal simulé."""
    source = tmp_path / "source"
    source.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    state = tmp_path / "state"
    state.mkdir()
    fake = tmp_path / "proton-drive"
    fake.write_text(FAKE_PROTON, encoding="utf-8")
    fake.chmod(0o755)

    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    monkeypatch.setattr(databackup, "BACKUP_DIR", backup)
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    monkeypatch.setattr(databackup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(databackup, "PROTON_DRIVE", fake)
    monkeypatch.setattr(databackup, "is_interactive", lambda: True)
    monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, "mot-de-passe-de-test")
    monkeypatch.setenv("FAKE_STATE", str(state))
    return tmp_path


def _state(project: Path, name: str) -> Path:
    return project / "state" / name


def _uploads(project: Path) -> list[str]:
    uploaded = _state(project, "uploaded")
    return sorted(path.name for path in uploaded.glob("*")) if uploaded.is_dir() else []


def _calls(project: Path) -> list[str]:
    log = _state(project, "calls.log")
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _put_archive(project: Path, name: str) -> None:
    (project / "backup" / name).write_bytes(b"archive")


# --- Cas nominal ------------------------------------------------------------


def test_transfer_uploads_each_archive(project: Path) -> None:
    _put_archive(project, "photos.zip")
    _put_archive(project, "documents.zip")

    assert databackup.main(["transfer"]) == databackup.EXIT_OK

    assert _uploads(project) == ["documents.zip", "photos.zip"]
    assert _calls(project)[0].startswith("filesystem upload -f replace ")
    assert _calls(project)[0].endswith(databackup.PROTON_PARENT)
    # ``transfer`` seul laisse les archives en place (cf. cdc.md §6)
    assert sorted(path.name for path in (project / "backup").glob("*.zip")) == ["documents.zip", "photos.zip"]


def test_no_archive_is_a_noop(project: Path) -> None:
    assert databackup.main(["transfer"]) == databackup.EXIT_OK
    assert _calls(project) == []


def test_dry_run_sends_nothing(project: Path) -> None:
    _put_archive(project, "photos.zip")

    assert databackup.main(["transfer", "--dry-run"]) == databackup.EXIT_OK

    assert _calls(project) == []
    assert (project / "backup" / "photos.zip").exists()


# --- Échecs -----------------------------------------------------------------


def test_failure_is_counted_and_run_continues(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "proton_login", lambda: False)
    _state(project, "fail_always").touch()
    _put_archive(project, "a.zip")
    _put_archive(project, "b.zip")

    assert databackup.main(["transfer"]) == databackup.EXIT_ERROR

    assert _uploads(project) == []
    assert len(_calls(project)) == 2  # les DEUX archives ont été tentées : le run continue


def test_login_then_retry_succeeds_in_terminal(project: Path) -> None:
    _state(project, "fail_once").touch()  # le premier upload échoue, le suivant réussit
    _state(project, "login_ok").touch()
    _put_archive(project, "photos.zip")

    assert databackup.main(["transfer"]) == databackup.EXIT_OK

    assert _uploads(project) == ["photos.zip"]
    calls = _calls(project)
    assert calls[0].startswith("filesystem upload")
    assert calls[1] == "auth login"
    assert calls[2].startswith("filesystem upload")


def test_failure_without_terminal_returns_4(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "is_interactive", lambda: False)
    _state(project, "fail_always").touch()
    _put_archive(project, "a.zip")
    _put_archive(project, "b.zip")

    assert databackup.main(["transfer"]) == databackup.EXIT_AUTH

    calls = _calls(project)
    assert len(calls) == 1  # arrêt après le premier échec
    assert all("auth login" not in call for call in calls)  # aucune tentative hors terminal


def test_missing_binary_fails(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "PROTON_DRIVE", project / "absent")
    _put_archive(project, "a.zip")

    assert databackup.main(["transfer"]) == databackup.EXIT_ERROR
    assert _uploads(project) == []


def test_transfer_fails_when_backup_missing(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "BACKUP_DIR", project / "absent")
    assert databackup.main(["transfer"]) == databackup.EXIT_BACKUP


# --- Enchaînement complet ---------------------------------------------------


def test_all_uploads_then_cleans_backup(project: Path) -> None:
    source = project / "source"
    (source / "Photos").mkdir()
    (source / "Photos" / "a.jpg").write_bytes(b"AAA")
    (source / "racine.odt").write_bytes(b"ODT")

    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploads(project) == ["documents.zip", "photos.zip"]
    assert list((project / "backup").iterdir()) == []  # nettoyage final (cf. cdc.md §6)

"""Tests de la sauvegarde incrémentale (I7) — cf. ``TODO.md`` et ``cdc.md`` §6.

Deux volets :

- **unitaire** : signature d'arborescence (métadonnées seules), statut d'une archive face à
  l'historique, lecture/écriture tolérante et atomique des fichiers d'état ;
- **bout en bout** : chaîne ``all`` avec une **doublure** de ``proton-drive`` — premier run
  complet, second run qui ne fait rien, dossier modifié en profondeur qui repart seul, échec
  d'upload **non** enregistré, historique corrompu, ``--full``, ``--dry-run``, ``--limit``,
  enchaînement ``archive`` puis ``transfer``, et invariants (``source/`` jamais modifiée).

Aucun réseau, aucun accès à l'historique réel de la machine (cf. ``tests/conftest.py``).
"""

from __future__ import annotations

import json
import os
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
    """Projet isolé + doublure de ``proton-drive`` + terminal simulé + historique isolé."""
    (tmp_path / "source").mkdir()
    (tmp_path / "backup").mkdir()
    (tmp_path / "fake").mkdir()
    fake = tmp_path / "proton-drive"
    fake.write_text(FAKE_PROTON, encoding="utf-8")
    fake.chmod(0o755)

    monkeypatch.setattr(databackup, "SOURCE_DIR", tmp_path / "source")
    monkeypatch.setattr(databackup, "BACKUP_DIR", tmp_path / "backup")
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    monkeypatch.setattr(databackup, "STATE_FILE", tmp_path / ".databackup-state.json")
    monkeypatch.setattr(databackup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(databackup, "PROTON_DRIVE", fake)
    monkeypatch.setattr(databackup, "is_interactive", lambda: True)
    monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, "mot-de-passe-de-test")
    monkeypatch.setenv("FAKE_STATE", str(tmp_path / "fake"))
    return tmp_path


# --- Utilitaires ------------------------------------------------------------


def _write(path: Path, content: bytes = b"data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _snapshot(root: Path) -> dict[str, tuple[int, int, int]]:
    """Empreinte du contenu de ``root`` (mode, taille, mtime) pour détecter toute écriture."""
    snapshot: dict[str, tuple[int, int, int]] = {}
    for path in sorted(root.rglob("*")):
        info = path.lstat()
        snapshot[str(path.relative_to(root))] = (info.st_mode, info.st_size, info.st_mtime_ns)
    return snapshot


def _signature(root: Path) -> str:
    files, _symlinks = databackup.collect_folder_files(root)
    return databackup.archive_signature(files, databackup.collect_empty_dirs(root), root)


def _state(project: Path) -> dict[str, dict[str, object]]:
    """Contenu de l'historique (``{}`` s'il n'existe pas encore)."""
    path = project / ".databackup-state.json"
    return json.loads(path.read_text(encoding="utf-8"))["archives"] if path.exists() else {}


def _calls(project: Path) -> list[str]:
    log = project / "fake" / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _uploaded(project: Path) -> list[str]:
    """Noms des archives réellement envoyées, dans l'ordre (cf. doublure)."""
    return [Path(call.split()[4]).name for call in _calls(project) if call.startswith("filesystem upload")]


def _log_content(project: Path) -> str:
    for handler in databackup.logger.handlers:
        handler.flush()
    return "\n".join(path.read_text(encoding="utf-8") for path in (project / "logs").glob("databackup-*.log"))


# --- Signature d'arborescence (cf. cdc.md §6) -------------------------------


def test_signature_is_stable_for_an_unchanged_tree(tmp_path: Path) -> None:
    root = tmp_path / "Divers"
    _write(root / "a.txt", b"AAA")
    _write(root / "sous" / "b.txt", b"BBB")
    (root / "vide").mkdir()

    first = _signature(root)

    assert first.startswith("sha256:")
    assert _signature(root) == first


def test_signature_depends_only_on_relative_content(tmp_path: Path) -> None:
    """Deux arborescences identiques à des emplacements différents ont la même signature."""
    for name in ("un", "deux"):
        root = tmp_path / name
        _write(root / "a.txt", b"AAA")
        _write(root / "sous" / "b.txt", b"BBB")
        os.utime(root / "a.txt", (1000, 1000))
        os.utime(root / "sous" / "b.txt", (2000, 2000))

    assert _signature(tmp_path / "un") == _signature(tmp_path / "deux")


def test_signature_changes_with_date_and_with_size(tmp_path: Path) -> None:
    root = tmp_path / "Divers"
    _write(root / "a.txt", b"AAA")
    os.utime(root / "a.txt", (5000, 5000))
    first = _signature(root)

    os.utime(root / "a.txt", (6000, 6000))  # même contenu, date différente
    assert _signature(root) != first

    root.joinpath("a.txt").write_bytes(b"AAA123")  # contenu plus long
    assert _signature(root) != first


def test_signature_sees_added_removed_and_empty_directories(tmp_path: Path) -> None:
    root = tmp_path / "Divers"
    _write(root / "a.txt", b"AAA")
    first = _signature(root)

    _write(root / "b.txt", b"BBB")
    added = _signature(root)
    assert added != first

    (root / "b.txt").unlink()
    assert _signature(root) != added

    (root / "vide").mkdir()  # sous-dossier vide : conservé dans l'archive, donc dans la signature
    assert _signature(root) != first


def test_signature_ignores_content_at_equal_size_and_date(tmp_path: Path) -> None:
    """Limite assumée (cf. cdc.md §6) : même taille **et** même date → même signature."""
    root = tmp_path / "Divers"
    _write(root / "a.txt", b"AAA")
    os.utime(root / "a.txt", (5000, 5000))
    first = _signature(root)

    root.joinpath("a.txt").write_bytes(b"BBB")  # même taille
    os.utime(root / "a.txt", (5000, 5000))  # même date
    assert _signature(root) == first


# --- Statut d'une archive face à l'historique -------------------------------


def _record(signature: str = "sha256:x", last_backup: str = "2026-10-18T14:25:11") -> databackup.ArchiveRecord:
    return databackup.ArchiveRecord(signature=signature, last_backup=last_backup)


def test_archive_status_without_history_is_new() -> None:
    assert databackup.archive_status("photos.zip", "sha256:x", {}) == (databackup.STATUS_NEW, None)


def test_archive_status_compares_signatures() -> None:
    known = {"photos.zip": _record("sha256:x")}

    assert databackup.archive_status("photos.zip", "sha256:x", known) == (
        databackup.STATUS_UNCHANGED,
        "2026-10-18T14:25:11",
    )
    assert databackup.archive_status("photos.zip", "sha256:y", known)[0] == databackup.STATUS_MODIFIED
    assert databackup.archive_status("photos.zip", "sha256:x", known, full=True)[0] == databackup.STATUS_MODIFIED


# --- Lecture et écriture de l'état ------------------------------------------


def test_state_round_trip_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / ".databackup-state.json"
    records = {
        "photos.zip": databackup.ArchiveRecord(
            signature="sha256:x", files=3, source_bytes=10, archive_bytes=9, last_backup="2026-10-18T14:25:11"
        )
    }

    assert databackup.save_records(path, records) is True

    assert databackup.load_records(path, "historique") == records
    assert not path.with_name(path.name + ".tmp").exists()  # aucun résidu temporaire


def test_missing_state_is_empty(tmp_path: Path) -> None:
    assert databackup.load_records(tmp_path / "absent.json", "historique") == {}


@pytest.mark.parametrize("content", ["pas du json", "{}", '{"archives": []}', '{"archives": {"a.zip": {}}}'])
def test_unreadable_state_is_ignored(tmp_path: Path, content: str) -> None:
    """Un état de travers ne fait jamais échouer un run : défaut sûr = sauvegarde complète."""
    path = tmp_path / ".databackup-state.json"
    path.write_text(content, encoding="utf-8")

    assert databackup.load_records(path, "historique") == {}


def test_unwritable_state_is_reported_without_raising(tmp_path: Path) -> None:
    path = tmp_path / ".databackup-state.json"
    path.mkdir()  # un dossier à la place du fichier : l'écriture est impossible

    assert databackup.save_records(path, {"photos.zip": _record()}) is False

    assert not path.with_name(path.name + ".tmp").exists()  # rien n'est laissé derrière


# --- Filtrage du plan -------------------------------------------------------


def test_plan_archives_filters_unchanged_folders(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg")
    _write(project / "source" / "Divers" / "a.txt")

    first = databackup.plan_archives()
    assert [plan.archive_name for plan in first.plans] == ["divers.zip", "photos.zip"]
    assert first.unchanged == []

    known = {
        plan.archive_name: databackup.ArchiveRecord(signature=plan.signature, last_backup="2026-01-01T00:00:00")
        for plan in first.plans
    }
    second = databackup.plan_archives(state=known)

    assert second.plans == []
    assert [plan.archive_name for plan in second.unchanged] == ["divers.zip", "photos.zip"]
    assert second.unchanged[0].last_backup == "2026-01-01T00:00:00"
    assert second.unchanged[0].status == databackup.STATUS_UNCHANGED


def test_collision_is_detected_even_when_a_folder_is_unchanged(project: Path) -> None:
    """La détection de collision porte sur **toutes** les archives, y compris les ignorées."""
    photos = project / "source" / "Photos"
    _write(photos / "a.jpg", b"AAA")
    _write(project / "source" / "photos" / "b.jpg", b"BBB")
    known = {"photos.zip": databackup.ArchiveRecord(signature=_signature(photos))}

    with pytest.raises(databackup.ScanError, match="Collision"):
        databackup.plan_archives(state=known)


# --- Bout en bout : premier run, puis rien à faire --------------------------


def test_first_run_backs_up_everything_and_records_history(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    _write(project / "source" / "Divers" / "note.txt", b"BBB")
    _write(project / "source" / "racine.odt", b"ODT")

    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["divers.zip", "documents.zip", "photos.zip"]
    records = _state(project)
    assert sorted(records) == ["divers.zip", "documents.zip", "photos.zip"]
    assert str(records["photos.zip"]["signature"]).startswith("sha256:")
    assert records["photos.zip"]["files"] == 1
    assert records["photos.zip"]["archive_bytes"]  # taille de l'archive réellement créée
    assert records["photos.zip"]["last_backup"]
    assert list((project / "backup").iterdir()) == []  # manifeste vidé avec les archives
    assert "Historique mis à jour : 3 archive(s)" in _log_content(project)


def test_second_run_without_change_does_nothing(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    _write(project / "source" / "Divers" / "note.txt", b"BBB")
    assert databackup.main(["all"]) == databackup.EXIT_OK
    before = _state(project)

    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert len(_calls(project)) == 2  # aucun upload supplémentaire
    assert list((project / "backup").iterdir()) == []  # rien n'a même été réécrit
    assert _state(project) == before
    content = _log_content(project)
    assert "[inchangé] Photos -> photos.zip" in content
    assert "Archives ignorées (déjà à jour) : 2." in content


# --- Bout en bout : ce qui déclenche une nouvelle sauvegarde ----------------


def test_deep_change_retriggers_only_that_folder(project: Path) -> None:
    deep = project / "source" / "Photos" / "sous" / "n1" / "n2" / "deep.jpg"
    _write(deep, b"AAA")
    _write(project / "source" / "Divers" / "note.txt", b"BBB")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    _write(deep, b"AAA modifie")  # 5 niveaux plus bas
    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["divers.zip", "photos.zip", "photos.zip"]


def test_added_then_removed_file_retriggers_the_folder(project: Path) -> None:
    _write(project / "source" / "Divers" / "a.txt", b"A")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    _write(project / "source" / "Divers" / "b.txt", b"B")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    (project / "source" / "Divers" / "b.txt").unlink()
    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["divers.zip", "divers.zip", "divers.zip"]


def test_new_empty_subdirectory_retriggers_the_folder(project: Path) -> None:
    _write(project / "source" / "Divers" / "a.txt", b"A")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    (project / "source" / "Divers" / "vide").mkdir()
    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["divers.zip", "divers.zip"]


def test_new_folder_is_included(project: Path) -> None:
    _write(project / "source" / "Divers" / "a.txt", b"A")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["divers.zip", "photos.zip"]


# --- Bout en bout : échecs, options et invariants ---------------------------


def test_failed_upload_is_not_recorded_then_retried(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    monkeypatch.setattr(databackup, "proton_login", lambda: False)
    (project / "fake" / "fail_always").touch()

    assert databackup.main(["all"]) == databackup.EXIT_ERROR

    assert _state(project) == {}  # rien d'enregistré : le dossier n'est pas « à jour »

    (project / "fake" / "fail_always").unlink()
    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["photos.zip", "photos.zip"]
    assert sorted(_state(project)) == ["photos.zip"]


def test_corrupted_history_falls_back_to_a_full_backup(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    assert databackup.main(["all"]) == databackup.EXIT_OK
    (project / ".databackup-state.json").write_text("{ pas du json", encoding="utf-8")

    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["photos.zip", "photos.zip"]
    assert "illisible" in _log_content(project)
    assert sorted(_state(project)) == ["photos.zip"]  # l'historique est réécrit sain


def test_full_option_ignores_history(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    assert databackup.main(["all"]) == databackup.EXIT_OK
    assert databackup.main(["all"]) == databackup.EXIT_OK
    assert _uploaded(project) == ["photos.zip"]  # le second run n'a rien envoyé

    assert databackup.main(["all", "--full"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["photos.zip", "photos.zip"]
    assert "l'historique est ignoré" in _log_content(project)


def test_dry_run_writes_no_history(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")

    assert databackup.main(["all", "--dry-run"]) == databackup.EXIT_OK

    assert _uploaded(project) == []
    assert not (project / ".databackup-state.json").exists()
    assert list((project / "backup").iterdir()) == []


def test_limit_records_only_the_archives_transferred(project: Path) -> None:
    _write(project / "source" / "Aaa" / "a.txt", b"A")
    _write(project / "source" / "Bbb" / "b.txt", b"B")
    _write(project / "source" / "racine.odt", b"ODT")

    assert databackup.main(["all", "--limit", "1"]) == databackup.EXIT_OK

    # ``documents.zip`` reste toujours traité (fichiers racine) ; ``bbb.zip`` reste à faire.
    assert sorted(_state(project)) == ["aaa.zip", "documents.zip"]

    assert databackup.main(["all"]) == databackup.EXIT_OK

    assert _uploaded(project) == ["aaa.zip", "documents.zip", "bbb.zip"]


def test_archive_then_transfer_updates_history(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")

    assert databackup.main(["archive"]) == databackup.EXIT_OK
    assert _state(project) == {}  # l'archivage seul ne marque rien comme sauvegardé
    assert (project / "backup" / databackup.MANIFEST_NAME).is_file()  # manifeste conservé

    assert databackup.main(["transfer"]) == databackup.EXIT_OK

    assert sorted(_state(project)) == ["photos.zip"]


def test_transfer_without_manifest_does_not_update_history(project: Path) -> None:
    (project / "backup" / "photos.zip").write_bytes(b"archive")

    assert databackup.main(["transfer"]) == databackup.EXIT_OK

    assert _state(project) == {}
    assert "Manifeste absent" in _log_content(project)


def test_scan_neither_writes_nor_records(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")

    assert databackup.main(["scan"]) == databackup.EXIT_OK

    assert not (project / ".databackup-state.json").exists()
    assert list((project / "backup").iterdir()) == []


def test_incremental_never_modifies_source(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    _write(project / "source" / "Divers" / "note.txt", b"BBB")
    _write(project / "source" / "racine.odt", b"ODT")
    before = _snapshot(project / "source")

    assert databackup.main(["all"]) == databackup.EXIT_OK
    assert databackup.main(["all"]) == databackup.EXIT_OK  # run « rien à faire »

    assert _snapshot(project / "source") == before

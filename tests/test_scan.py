"""Tests de l'étape « scan » (I2) — cf. ``TODO.md``.

Vérifie le nommage normalisé, la construction du plan (dossiers de premier niveau,
``documents.zip`` pour la racine), les exclusions (dossiers vides), les liens symboliques,
la détection des collisions et l'absence de toute écriture dans ``source/``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import databackup


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


@pytest.fixture
def source(tmp_path: Path) -> Path:
    folder = tmp_path / "source"
    folder.mkdir()
    return folder


# --- Nommage normalisé (cf. cdc.md §4) --------------------------------------


@pytest.mark.parametrize(
    ("folder_name", "expected"),
    [
        ("Skills et modèles IA", "skills-et-modeles-ia"),
        ("Garanties - modes d'emploi", "garanties-modes-d-emploi"),
        ("Complotiste !", "complotiste"),
        ("Places de camp", "places-de-camp"),
        ("Été 2026", "ete-2026"),
        ("Photos", "photos"),
    ],
)
def test_normalize_archive_name(folder_name: str, expected: str) -> None:
    assert databackup.normalize_archive_name(folder_name) == expected


# --- Construction du plan ---------------------------------------------------


def test_one_archive_per_first_level_folder(source: Path) -> None:
    _write(source / "Photos" / "a.jpg")
    _write(source / "Photos" / "sous" / "b.jpg")
    _write(source / "Divers" / "note.txt")

    report = databackup.plan_archives(source_dir=source)

    assert [plan.archive_name for plan in report.plans] == ["divers.zip", "photos.zip"]
    photos = next(plan for plan in report.plans if plan.archive_name == "photos.zip")
    assert photos.file_count == 2  # récursif
    assert photos.total_size == 8  # 2 x b"data"
    assert photos.origin == source / "Photos"


def test_root_files_go_to_documents_zip(source: Path) -> None:
    _write(source / "Photos" / "a.jpg")
    _write(source / "racine.odt")
    _write(source / "Compta Homebank.xhb~")  # temporaire : inclus (aucun filtrage)
    _write(source / ".cache")  # caché : inclus

    report = databackup.plan_archives(source_dir=source)

    documents = next(plan for plan in report.plans if plan.archive_name == "documents.zip")
    assert documents.label == "fichiers racine"
    assert documents.file_count == 3


def test_no_documents_zip_without_root_files(source: Path) -> None:
    _write(source / "Photos" / "a.jpg")
    report = databackup.plan_archives(source_dir=source)
    assert "documents.zip" not in [plan.archive_name for plan in report.plans]


def test_empty_first_level_folder_is_excluded(source: Path) -> None:
    _write(source / "Photos" / "a.jpg")
    (source / "Vide").mkdir()

    report = databackup.plan_archives(source_dir=source)

    assert [plan.label for plan in report.plans] == ["Photos"]
    assert [path.name for path in report.excluded] == ["Vide"]


def test_folder_with_only_empty_subdirs_is_excluded(source: Path) -> None:
    (source / "Presque" / "vide1" / "vide2").mkdir(parents=True)
    report = databackup.plan_archives(source_dir=source)
    assert report.plans == []
    assert [path.name for path in report.excluded] == ["Presque"]


def test_limit_keeps_first_folders_and_root(source: Path) -> None:
    _write(source / "Aaa" / "a.txt")
    _write(source / "Bbb" / "b.txt")
    _write(source / "Ccc" / "c.txt")
    _write(source / "racine.odt")

    report = databackup.plan_archives(source_dir=source, limit=2)

    assert [plan.archive_name for plan in report.plans] == ["aaa.zip", "bbb.zip", "documents.zip"]


def test_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(databackup.ScanError, match="introuvable"):
        databackup.plan_archives(source_dir=tmp_path / "absent")


# --- Liens symboliques ------------------------------------------------------


def test_internal_symlinks_are_ignored_and_reported(source: Path) -> None:
    divers = source / "Divers"
    _write(divers / "note.txt")
    os.symlink(source / "Divers", source / "lien-dossier")
    os.symlink(divers / "note.txt", divers / "lien-fichier")

    report = databackup.plan_archives(source_dir=source)

    divers_plan = next(plan for plan in report.plans if plan.label == "Divers")
    assert divers_plan.file_count == 1  # le lien vers note.txt n'est pas compté
    assert {path.name for path in report.symlinks} == {"lien-dossier", "lien-fichier"}


def test_symlink_loop_is_not_followed(source: Path) -> None:
    boucle = source / "Boucle"
    _write(boucle / "a.txt")
    os.symlink(boucle, boucle / "self")

    report = databackup.plan_archives(source_dir=source)

    assert next(plan for plan in report.plans).file_count == 1


# --- Collisions (cf. cdc.md §4) ---------------------------------------------


def test_collision_between_folders_fails(source: Path) -> None:
    _write(source / "Photos" / "a.jpg")
    _write(source / "photos" / "b.jpg")

    with pytest.raises(databackup.ScanError, match="Collision"):
        databackup.plan_archives(source_dir=source)


def test_collision_with_documents_zip_fails(source: Path) -> None:
    _write(source / "Documents" / "a.odt")
    _write(source / "racine.odt")

    with pytest.raises(databackup.ScanError, match=r"documents\.zip"):
        databackup.plan_archives(source_dir=source)


def test_empty_normalized_name_fails(source: Path) -> None:
    _write(source / "!!!" / "a.txt")
    with pytest.raises(databackup.ScanError, match="vide"):
        databackup.plan_archives(source_dir=source)


# --- Étape et non-écriture --------------------------------------------------


def test_step_scan_returns_error_on_conflict(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    _write(source / "Photos" / "a.jpg")
    _write(source / "photos" / "b.jpg")
    assert databackup.step_scan() == databackup.EXIT_ERROR


def test_scan_does_not_modify_source(source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    _write(source / "Photos" / "a.jpg")
    _write(source / "Photos" / "sous" / "b.jpg")
    _write(source / "racine.odt")
    (source / "Vide").mkdir()
    os.symlink(source / "Photos", source / "lien")

    before = _snapshot(source)
    assert databackup.main(["scan"]) == databackup.EXIT_OK
    assert _snapshot(source) == before


def test_dry_run_scan_logs_plan_and_target(source: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    _write(source / "Photos" / "a.jpg")

    assert databackup.main(["scan", "--dry-run"]) == databackup.EXIT_OK

    for handler in databackup.logger.handlers:
        handler.flush()
    content = "\n".join(path.read_text(encoding="utf-8") for path in (tmp_path / "logs").glob("databackup-*.log"))
    assert "photos.zip" in content
    assert databackup.PROTON_PARENT in content

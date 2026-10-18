"""Tests de l'étape « archive » (I3) — cf. ``TODO.md``.

Vérifie le chiffrement AES-256, la préservation de l'arborescence interne (chemins relatifs,
sous-dossiers vides), le choix stocké/dégonflé selon l'extension, ``documents.zip``, le
vidage initial de ``backup/``, la résolution du mot de passe et la non-modification des sources.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import pyzipper

import databackup

PASSWORD = "mot-de-passe-de-test"


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


def _namelist(archive_path: Path, password: str = PASSWORD) -> list[str]:
    with pyzipper.AESZipFile(archive_path) as archive:
        archive.setpassword(password.encode("utf-8"))
        return archive.namelist()


def _read(archive_path: Path, name: str, password: str = PASSWORD) -> bytes:
    with pyzipper.AESZipFile(archive_path) as archive:
        archive.setpassword(password.encode("utf-8"))
        return archive.read(name)


def _aes_strength(info: pyzipper.ZipInfo) -> int | None:
    """Force du chiffrement AES d'une entrée (1=128, 2=192, 3=256), lue dans le champ 0x9901."""
    extra = info.extra
    offset = 0
    while offset + 4 <= len(extra):
        header_id = int.from_bytes(extra[offset : offset + 2], "little")
        size = int.from_bytes(extra[offset + 2 : offset + 4], "little")
        data = extra[offset + 4 : offset + 4 + size]
        if header_id == 0x9901 and size >= 5:
            return data[4]
        offset += 4 + size
    return None


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isole le projet dans un dossier temporaire et fournit un mot de passe d'essai."""
    source = tmp_path / "source"
    source.mkdir()
    backup = tmp_path / "backup"
    backup.mkdir()
    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    monkeypatch.setattr(databackup, "BACKUP_DIR", backup)
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    monkeypatch.setattr(databackup, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, PASSWORD)
    return tmp_path


def _archive_of(project: Path, folder_name: str) -> Path:
    """Crée une archive pour un dossier unique de ``source`` et retourne son chemin."""
    report = databackup.plan_archives(source_dir=project / "source", limit=1)
    plan = next(plan for plan in report.plans if plan.label == folder_name)
    destination = project / "backup" / plan.archive_name
    databackup.write_archive(plan, destination, PASSWORD)
    return destination


# --- Contenu de l'archive ---------------------------------------------------


def test_preserves_relative_paths(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg", b"AAA")
    _write(source / "Photos" / "sous" / "b.txt", b"BBB")

    archive = _archive_of(project, "Photos")

    assert _namelist(archive) == ["a.jpg", "sous/b.txt"]
    assert _read(archive, "sous/b.txt") == b"BBB"


def test_empty_subdirs_are_preserved(project: Path) -> None:
    source = project / "source"
    _write(source / "Maison" / "a.txt")
    (source / "Maison" / "vide" / "profond").mkdir(parents=True)

    names = _namelist(_archive_of(project, "Maison"))

    assert "vide/" in names
    assert "vide/profond/" in names


def test_documents_zip_holds_root_files(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg")
    _write(source / "racine.odt", b"ODT")
    _write(source / "Compta Homebank.xhb~", b"TMP")

    report = databackup.plan_archives(source_dir=source)
    documents = next(plan for plan in report.plans if plan.archive_name == "documents.zip")
    archive = project / "backup" / "documents.zip"
    stats = databackup.write_archive(documents, archive, PASSWORD)

    assert stats.file_count == 2
    assert sorted(_namelist(archive)) == ["Compta Homebank.xhb~", "racine.odt"]


# --- Chiffrement et compression ---------------------------------------------


def test_archive_is_encrypted_aes_256(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg", b"AAA")

    archive = _archive_of(project, "Photos")

    with pyzipper.AESZipFile(archive) as handle:
        info = handle.getinfo("a.jpg")
        assert info.flag_bits & 0x1  # entrée marquée chiffrée
        assert _aes_strength(info) == 3  # 3 = AES-256
        with pytest.raises(RuntimeError):
            handle.read("a.jpg")  # refus sans mot de passe
        handle.setpassword(b"mauvais")
        with pytest.raises(RuntimeError):
            handle.read("a.jpg")  # refus avec un mauvais mot de passe

    assert _read(archive, "a.jpg") == b"AAA"


def test_stored_extensions_are_not_compressed(project: Path) -> None:
    source = project / "source"
    _write(source / "Prusa" / "piece.stl", b"x" * 5000)
    _write(source / "Prusa" / "piece.pdf", b"y" * 5000)

    archive = _archive_of(project, "Prusa")

    with pyzipper.AESZipFile(archive) as handle:
        handle.setpassword(PASSWORD.encode("utf-8"))
        assert handle.getinfo("piece.stl").compress_type == pyzipper.ZIP_STORED
        assert handle.getinfo("piece.pdf").compress_type == pyzipper.ZIP_DEFLATED


# --- Étape et effets sur ``backup/`` ----------------------------------------


def test_archive_command_builds_all_archives(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg")
    _write(source / "Divers" / "note.txt")
    _write(source / "racine.odt")

    assert databackup.main(["archive"]) == databackup.EXIT_OK

    names = sorted(path.name for path in (project / "backup").glob("*.zip"))
    assert names == ["divers.zip", "documents.zip", "photos.zip"]


def test_archive_empties_backup_first(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg")
    stale = project / "backup" / "vieux.zip"
    stale.write_bytes(b"residu")

    assert databackup.main(["archive"]) == databackup.EXIT_OK

    assert not stale.exists()
    assert (project / "backup" / "photos.zip").exists()  # ``archive`` seul laisse ses archives


def test_archive_dry_run_writes_nothing(project: Path) -> None:
    _write(project / "source" / "Photos" / "a.jpg")

    assert databackup.main(["archive", "--dry-run"]) == databackup.EXIT_OK

    assert list((project / "backup").iterdir()) == []


def test_limit_applies_to_archive(project: Path) -> None:
    source = project / "source"
    _write(source / "Aaa" / "a.txt")
    _write(source / "Bbb" / "b.txt")
    _write(source / "racine.odt")

    assert databackup.main(["archive", "--limit", "1"]) == databackup.EXIT_OK

    names = sorted(path.name for path in (project / "backup").glob("*.zip"))
    assert names == ["aaa.zip", "documents.zip"]


def test_archive_fails_when_backup_missing(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(project / "source" / "Photos" / "a.jpg")
    monkeypatch.setattr(databackup, "BACKUP_DIR", project / "absent")
    assert databackup.main(["archive"]) == databackup.EXIT_BACKUP


# --- Mot de passe -----------------------------------------------------------


def test_missing_password_fails_without_writing(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(project / "source" / "Photos" / "a.jpg")
    monkeypatch.delenv(databackup.PASSWORD_ENV_VAR, raising=False)

    assert databackup.main(["archive"]) == databackup.EXIT_ERROR
    assert list((project / "backup").glob("*.zip")) == []


def test_password_read_from_env_file(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(project / "source" / "Photos" / "a.jpg", b"AAA")
    monkeypatch.delenv(databackup.PASSWORD_ENV_VAR, raising=False)
    (project / ".env").write_text(f"{databackup.PASSWORD_ENV_VAR}={PASSWORD}\n", encoding="utf-8")

    assert databackup.main(["archive"]) == databackup.EXIT_OK
    assert _read(project / "backup" / "photos.zip", "a.jpg") == b"AAA"


# --- Robustesse -------------------------------------------------------------


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignore les permissions de fichier")
def test_unreadable_file_is_skipped(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "ok.txt", b"OK")
    bad = _write(source / "Photos" / "bad.txt", b"BAD")
    bad.chmod(0o000)

    try:
        archive = _archive_of(project, "Photos")
    finally:
        bad.chmod(0o644)

    assert _namelist(archive) == ["ok.txt"]


def test_timestamp_before_1980_is_archived_with_clamped_date(project: Path) -> None:
    source = project / "source"
    old = _write(source / "Prusa" / "vieil.stl", b"x" * 10)
    os.utime(old, (0, 0))  # 1970-01-01 : hors plage ZIP

    archive = _archive_of(project, "Prusa")

    assert _namelist(archive) == ["vieil.stl"]  # le fichier est bien sauvegardé
    with pyzipper.AESZipFile(archive) as handle:
        handle.setpassword(PASSWORD.encode("utf-8"))
        assert handle.getinfo("vieil.stl").date_time == (1980, 1, 1, 0, 0, 0)


def test_file_refused_by_the_format_is_skipped(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = project / "source"
    _write(source / "Photos" / "ok.txt", b"OK")
    _write(source / "Photos" / "bad.txt", b"BAD")
    real_compress_type = databackup._compress_type

    def flaky(path: Path) -> int:
        if path.name == "bad.txt":
            raise ValueError("simulation d'un fichier refusé par le format")
        return real_compress_type(path)

    monkeypatch.setattr(databackup, "_compress_type", flaky)

    archive = _archive_of(project, "Photos")

    assert _namelist(archive) == ["ok.txt"]  # l'erreur d'un fichier n'interrompt pas l'archive


def test_stats_count_created_archives_even_before_a_later_failure(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = project / "source"
    _write(source / "Aaa" / "a.txt")
    _write(source / "Bbb" / "b.txt")
    real_write = databackup.write_archive
    calls = {"count": 0}

    def flaky(plan: databackup.ArchivePlan, destination: Path, password: str) -> databackup.ArchiveStats:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("disque plein (simulation)")
        return real_write(plan, destination, password)

    monkeypatch.setattr(databackup, "write_archive", flaky)
    stats = databackup.RunStats()

    assert databackup.step_archive(stats=stats) == databackup.EXIT_ERROR

    assert stats.archives_planned == 2
    assert stats.archives_created == 1  # le premier est compté malgré l'échec du second
    assert stats.archive_volume > 0


def test_empty_source_creates_nothing(project: Path) -> None:
    assert databackup.main(["archive"]) == databackup.EXIT_OK
    assert list((project / "backup").iterdir()) == []


def test_sources_are_not_modified(project: Path) -> None:
    source = project / "source"
    _write(source / "Photos" / "a.jpg")
    _write(source / "Photos" / "sous" / "b.txt")
    _write(source / "racine.odt")
    (source / "Vide").mkdir()

    before = _snapshot(source)
    assert databackup.main(["archive"]) == databackup.EXIT_OK
    assert _snapshot(source) == before

"""Tests du socle technique (I1) — cf. ``TODO.md``.

Couvre le parseur d'arguments, le journal (rotation incluse), le verrou, la résolution
du mot de passe et le contrat de processus (code 5 quand un run est en cours, arrêt
propre sur SIGTERM, ``--dry-run`` sans effet).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import databackup

MODULE_PATH = Path(databackup.__file__).resolve()
START_SCRIPT = MODULE_PATH.parent / "start.sh"


@pytest.fixture
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isole le projet dans un dossier temporaire (source, backup, logs, verrou, .env)."""
    backup = tmp_path / "backup"
    backup.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(databackup, "SOURCE_DIR", source)
    monkeypatch.setattr(databackup, "BACKUP_DIR", backup)
    monkeypatch.setattr(databackup, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(databackup, "LOCK_FILE", tmp_path / ".databackup.lock")
    monkeypatch.setattr(databackup, "ENV_FILE", tmp_path / ".env")
    # Un run ``all``/``archive`` exige un mot de passe (I3) : la fixture en fournit un.
    monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, "mot-de-passe-de-test")
    return tmp_path


@pytest.fixture
def isolated_project(tmp_path: Path) -> Path:
    """Copie le module dans un dossier temporaire (PROJECT_DIR = ce dossier)."""
    shutil.copy(MODULE_PATH, tmp_path / "databackup.py")
    (tmp_path / "backup").mkdir()
    return tmp_path


def _dead_pid() -> int:
    """Retourne un PID garanti inactif (processus lancé puis terminé)."""
    process = subprocess.Popen([sys.executable, "-c", "pass"], stdout=subprocess.DEVNULL)
    pid = process.pid
    process.wait()
    return pid


def _flush_logs() -> None:
    for handler in databackup.logger.handlers:
        handler.flush()


# --- Parseur d'arguments ----------------------------------------------------


class TestParseArgs:
    def test_named_command(self) -> None:
        assert databackup.parse_args(["archive"]).command == "archive"

    def test_no_command_leaves_none(self) -> None:
        assert databackup.parse_args([]).command is None

    def test_dry_run_and_limit(self) -> None:
        args = databackup.parse_args(["all", "--dry-run", "--limit", "3"])
        assert args.dry_run is True
        assert args.limit == 3

    def test_defaults(self) -> None:
        args = databackup.parse_args(["transfer"])
        assert args.dry_run is False
        assert args.limit is None

    def test_unknown_command_exits_2(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            databackup.parse_args(["frobnicate"])
        assert excinfo.value.code == databackup.EXIT_USAGE

    def test_invalid_limit_exits_2(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            databackup.parse_args(["scan", "--limit", "beaucoup"])
        assert excinfo.value.code == databackup.EXIT_USAGE


# --- Journalisation ---------------------------------------------------------


class TestLogging:
    def test_creates_timestamped_log(self, sandbox: Path) -> None:
        log_path = databackup.setup_logging()
        assert log_path.is_file()
        assert log_path.parent == sandbox / "logs"
        assert log_path.name.startswith("databackup-")

    def test_rotation_keeps_latest(self, sandbox: Path) -> None:
        logs_dir = sandbox / "logs"
        logs_dir.mkdir()
        for index in range(10):
            (logs_dir / f"databackup-2026010{index}-000000.log").write_text("ancien", encoding="utf-8")

        databackup.setup_logging()

        remaining = sorted(p.name for p in logs_dir.glob("databackup-*.log"))
        assert len(remaining) == databackup.LOG_KEEP

    def test_rotation_keeps_everything_when_fewer_than_keep(self, sandbox: Path) -> None:
        logs_dir = sandbox / "logs"
        logs_dir.mkdir()
        for index in range(3):
            (logs_dir / f"databackup-2026010{index}-000000.log").write_text("ancien", encoding="utf-8")

        databackup.setup_logging()

        remaining = sorted(p.name for p in logs_dir.glob("databackup-*.log"))
        assert len(remaining) == 4  # les 3 anciens + le nouveau


# --- Mot de passe des archives ---------------------------------------------


class TestPassword:
    def test_environment_variable_wins(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, "depuis-env")
        (sandbox / ".env").write_text(f"{databackup.PASSWORD_ENV_VAR}=depuis-fichier\n", encoding="utf-8")
        assert databackup.resolve_password() == "depuis-env"

    def test_reads_env_file(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(databackup.PASSWORD_ENV_VAR, raising=False)
        (sandbox / ".env").write_text(
            '# commentaire ignoré\nexport DATABACKUP_ZIP_PASSWORD = "secret" \nAUTRE=valeur\n',
            encoding="utf-8",
        )
        assert databackup.resolve_password() == "secret"

    def test_missing_returns_none(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(databackup.PASSWORD_ENV_VAR, raising=False)
        assert databackup.resolve_password() is None

    def test_log_never_contains_the_secret(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(databackup.PASSWORD_ENV_VAR, "topsecret")
        log_path = databackup.setup_logging()
        databackup.log_password_source()
        _flush_logs()

        content = log_path.read_text(encoding="utf-8")
        assert "topsecret" not in content
        assert databackup.PASSWORD_ENV_VAR in content


# --- Verrou -----------------------------------------------------------------


class TestLock:
    def test_acquire_writes_pid_then_release(self, sandbox: Path) -> None:
        lock = sandbox / ".databackup.lock"
        databackup.acquire_lock()
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
        databackup.release_lock()
        assert not lock.exists()

    def test_second_acquire_is_refused(self, sandbox: Path) -> None:
        databackup.acquire_lock()
        try:
            with pytest.raises(databackup.LockError):
                databackup.acquire_lock()
        finally:
            databackup.release_lock()

    def test_stale_lock_is_recovered(self, sandbox: Path) -> None:
        lock = sandbox / ".databackup.lock"
        lock.write_text(f"{_dead_pid()}\n", encoding="utf-8")
        databackup.acquire_lock()
        assert lock.read_text(encoding="utf-8").strip() == str(os.getpid())
        databackup.release_lock()

    def test_command_returns_5_when_locked(self, sandbox: Path) -> None:
        lock = sandbox / ".databackup.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")
        assert databackup.main(["scan"]) == databackup.EXIT_LOCKED
        assert lock.exists()  # le verrou d'un autre run n'est jamais supprimé


# --- Commandes et effets ----------------------------------------------------


class TestCommands:
    def test_default_run_uses_all(self, sandbox: Path) -> None:
        assert databackup.main([]) == databackup.EXIT_OK

    def test_scan_succeeds(self, sandbox: Path) -> None:
        assert databackup.main(["scan"]) == databackup.EXIT_OK

    def test_all_fails_when_backup_missing(self, sandbox: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(databackup, "BACKUP_DIR", sandbox / "absent")
        assert databackup.main(["all"]) == databackup.EXIT_BACKUP

    def test_cleanup_empties_backup(self, sandbox: Path) -> None:
        (sandbox / "backup" / "photos.zip").write_bytes(b"x")
        (sandbox / "backup" / "sous-dossier").mkdir()
        assert databackup.main(["cleanup"]) == databackup.EXIT_OK
        assert list((sandbox / "backup").iterdir()) == []

    def test_all_empties_backup_at_the_end(self, sandbox: Path) -> None:
        (sandbox / "backup" / "photos.zip").write_bytes(b"x")
        assert databackup.main(["all"]) == databackup.EXIT_OK
        assert list((sandbox / "backup").iterdir()) == []

    def test_dry_run_writes_nothing(self, sandbox: Path) -> None:
        sentinel = sandbox / "backup" / "photos.zip"
        sentinel.write_bytes(b"x")
        assert databackup.main(["all", "--dry-run"]) == databackup.EXIT_OK
        assert sentinel.exists()  # backup/ intact
        assert not (sandbox / ".databackup.lock").exists()  # verrou libéré


# --- Contrat de processus ---------------------------------------------------


class TestProcessContract:
    def test_start_script_is_executable(self) -> None:
        assert os.access(START_SCRIPT, os.X_OK)
        assert "exec " in START_SCRIPT.read_text(encoding="utf-8")

    def test_second_run_refused_with_code_5(self, isolated_project: Path) -> None:
        lock = isolated_project / ".databackup.lock"
        lock.write_text(f"{os.getpid()}\n", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, "databackup.py", "scan"],
            cwd=isolated_project,
            capture_output=True,
            text=True,
        )

        assert result.returncode == databackup.EXIT_LOCKED
        assert lock.exists()

    def test_sigterm_releases_lock_and_empties_backup(self, isolated_project: Path) -> None:
        (isolated_project / "backup" / "photos.zip").write_bytes(b"x")
        runner = isolated_project / "runner.py"
        runner.write_text(
            "import sys, time\n"
            "import databackup\n"
            "def slow(*, limit=None, dry_run=False, stats=None):\n"
            "    time.sleep(60)\n"
            "    return 0\n"
            "databackup.step_scan = slow\n"
            "sys.exit(databackup.main(['all']))\n",
            encoding="utf-8",
        )

        process = subprocess.Popen(
            [sys.executable, "runner.py"],
            cwd=isolated_project,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        lock = isolated_project / ".databackup.lock"
        deadline = time.monotonic() + 10
        while not lock.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert lock.exists(), "le verrou n'a pas été créé"

        process.send_signal(signal.SIGTERM)

        assert process.wait(timeout=10) != 0
        assert not lock.exists()
        assert list((isolated_project / "backup").iterdir()) == []

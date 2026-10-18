#!/usr/bin/env python3
"""DataBackup — sauvegarde chiffrée des documents vers Proton Drive.

Étapes (cf. ``cdc.md`` §6 et §8) :

- ``scan`` : recense les dossiers de premier niveau et les fichiers racine à sauvegarder ;
- ``archive`` : crée un zip chiffré AES-256 par dossier dans ``backup/`` ;
- ``transfer`` : envoie les zips de ``backup/`` vers Proton Drive ;
- ``cleanup`` : vide ``backup/`` ;
- ``all`` : scan → archive → transfer, puis vidage de ``backup/`` (défaut).

**I1 — socle technique** : ce module ne contient encore aucune logique métier. Les étapes
``scan`` / ``archive`` / ``transfer`` sont des ébauches ; seule l'ossature est en place
(arguments, journalisation horodatée avec rotation, verrou PID, résolution du secret, codes
retour, arrêt propre sur SIGTERM / SIGINT, options ``--dry-run`` et ``--limit``).
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import sys
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

# --- Configuration ----------------------------------------------------------

PROJECT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = PROJECT_DIR / "source"
BACKUP_DIR = PROJECT_DIR / "backup"
LOGS_DIR = PROJECT_DIR / "logs"
LOCK_FILE = PROJECT_DIR / ".databackup.lock"
ENV_FILE = PROJECT_DIR / ".env"

# Binaire CLI Proton Drive (non versionné, installé par ./install.sh) — cf. cdc.md §5.
PROTON_DRIVE = PROJECT_DIR / "proton-drive"
PROTON_PARENT = "/my-files/databackup"

# Secret des archives : la variable d'environnement est prioritaire sur .env — cf. cdc.md §7.
PASSWORD_ENV_VAR = "DATABACKUP_ZIP_PASSWORD"

# Rotation des journaux : on ne conserve que les N derniers — cf. cdc.md §9.
LOG_KEEP = 7

# Commande appliquée quand aucune n'est fournie — cf. cdc.md §8.
DEFAULT_COMMAND = "all"

# Commandes dont le run se termine par un vidage de ``backup/`` — cf. cdc.md §6.
CLEANUP_COMMANDS = ("all", "cleanup")

# Codes retour — contrat start.sh / Piloter (cf. cdc.md §8).
EXIT_OK = 0
EXIT_ERROR = 1  # échec générique (archivage ou transfert)
EXIT_USAGE = 2  # argument invalide (aussi émis par argparse)
EXIT_BACKUP = 3  # dossier backup/ indisponible (disque non monté)
EXIT_AUTH = 4  # authentification Proton requise (utilisé en I4)
EXIT_LOCKED = 5  # sauvegarde déjà en cours (verrou)

logger = logging.getLogger("databackup")


# --- Exceptions -------------------------------------------------------------


class Cancelled(Exception):
    """Annulation demandée par SIGTERM / SIGINT."""


class BackupUnavailable(RuntimeError):
    """Le dossier temporaire ``backup/`` est absent ou non inscriptible (code retour 3)."""


class LockError(RuntimeError):
    """Un autre run est déjà en cours (code retour 5)."""


# --- Utilitaires ------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Formate une durée en ``H:MM:SS``."""
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def setup_logging(logs_dir: Path | None = None, keep: int = LOG_KEEP) -> Path:
    """Configure la journalisation (fichier horodaté + console) et fait tourner les logs.

    Retourne le chemin du fichier de log créé.
    """
    directory = logs_dir or LOGS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / f"databackup-{datetime.now():%Y%m%d-%H%M%S}.log"

    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    rotate_logs(directory, keep)
    return log_path


def rotate_logs(directory: Path, keep: int = LOG_KEEP) -> None:
    """Ne conserve que les ``keep`` journaux les plus récents."""
    logs = sorted(directory.glob("databackup-*.log"))
    for old in logs[: max(0, len(logs) - keep)]:
        old.unlink(missing_ok=True)


# --- Mot de passe des archives ----------------------------------------------


def parse_dotenv(text: str) -> dict[str, str]:
    """Analyse minimale d'un fichier ``.env`` : ``KEY=VALUE``, ``#`` commentaire.

    Gère le préfixe ``export``, les espaces autour du ``=`` et les guillemets autour
    de la valeur. Toute ligne sans ``=`` ou sans clé est ignorée.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def load_env_file(path: Path) -> dict[str, str]:
    """Charge un fichier ``.env`` s'il existe ; retourne un dictionnaire vide sinon."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    return parse_dotenv(text)


def resolve_password(env: Mapping[str, str] | None = None, env_file: Path | None = None) -> str | None:
    """Retourne le mot de passe des archives, ou ``None`` s'il est introuvable.

    Priorité : variable d'environnement ``DATABACKUP_ZIP_PASSWORD``, puis ``.env`` local.
    """
    environment = os.environ if env is None else env
    from_environment = environment.get(PASSWORD_ENV_VAR)
    if from_environment:
        return from_environment
    return load_env_file(env_file or ENV_FILE).get(PASSWORD_ENV_VAR) or None


def log_password_source(env_file: Path | None = None) -> None:
    """Journalise la *provenance* du mot de passe — jamais sa valeur (cf. cdc.md §11)."""
    path = env_file or ENV_FILE
    if os.environ.get(PASSWORD_ENV_VAR):
        logger.info("Mot de passe des archives : variable %s.", PASSWORD_ENV_VAR)
    elif load_env_file(path).get(PASSWORD_ENV_VAR):
        logger.info("Mot de passe des archives : fichier %s.", path.name)
    else:
        logger.warning(
            "Mot de passe des archives introuvable (ni %s, ni %s) — requis pour l'archivage (I3).",
            PASSWORD_ENV_VAR,
            path.name,
        )


# --- Verrou d'exécution -----------------------------------------------------


def read_lock_pid(path: Path) -> int | None:
    """Lit le PID inscrit dans le verrou ; ``None`` si absent ou illisible."""
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def pid_alive(pid: int) -> bool:
    """Indique si un processus portant ce PID est actif (best effort)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def acquire_lock(path: Path | None = None) -> None:
    """Crée le verrou (contenant le PID courant).

    Lève :class:`LockError` si un run est déjà en cours. Un verrou laissé par un
    processus disparu (``kill -9``) est considéré comme obsolète et repris.
    """
    lock_path = path or LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            pid = read_lock_pid(lock_path)
            if attempt == 0 and pid is not None and not pid_alive(pid):
                logger.warning("Verrou obsolète (%s, PID %s inactif) : reprise.", lock_path.name, pid)
                lock_path.unlink(missing_ok=True)
                continue
            raise LockError(f"Une sauvegarde est déjà en cours (verrou {lock_path.name}, PID {pid}).") from None
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\n")
        return
    raise LockError(f"Verrou {lock_path.name} impossible à acquérir.")


def release_lock(path: Path | None = None) -> None:
    """Supprime le verrou s'il existe."""
    (path or LOCK_FILE).unlink(missing_ok=True)


# --- Arrêt propre (SIGTERM / SIGINT) ----------------------------------------


def install_signal_handlers() -> None:
    """Installe l'arrêt propre sur SIGTERM / SIGINT (timeout Piloter, Ctrl-C) — cf. cdc.md §8."""
    signal.signal(signal.SIGTERM, _raise_cancelled)
    signal.signal(signal.SIGINT, _raise_cancelled)


def remove_signal_handlers() -> None:
    """Restaure le comportement par défaut des signaux."""
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.SIG_DFL)


def _raise_cancelled(_signum: int, _frame: object) -> None:
    raise Cancelled()


# --- Dossier temporaire ``backup/`` -----------------------------------------


def require_backup_dir(path: Path | None = None) -> None:
    """Vérifie que ``backup/`` existe et est inscriptible (cf. cdc.md §6, étape 1)."""
    backup = path or BACKUP_DIR
    if not backup.exists():
        raise BackupUnavailable(f"Dossier de backup introuvable : {backup} — le disque de backup est-il monté ?")
    if not os.access(backup, os.W_OK):
        raise BackupUnavailable(f"Dossier de backup non inscriptible : {backup}")


def empty_backup(path: Path | None = None) -> int:
    """Vide ``backup/``. Retourne le nombre d'éléments supprimés."""
    backup = path or BACKUP_DIR
    removed = 0
    for entry in backup.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()
        removed += 1
    return removed


def _final_cleanup() -> bool:
    """Vide ``backup/`` en fin de run. Retourne ``False`` si le vidage est impossible."""
    try:
        require_backup_dir()
        logger.info("Vidage de backup/ : %d élément(s) supprimé(s).", empty_backup())
    except (BackupUnavailable, OSError) as exc:
        logger.error("Vidage de backup/ impossible : %s", exc)
        return False
    return True


# --- Étapes (ébauches I1, logique à venir) ----------------------------------


def _log_stub(step: str, limit: int | None, dry_run: bool) -> None:
    details = []
    if limit is not None:
        details.append(f"limit={limit}")
    if dry_run:
        details.append("dry-run")
    suffix = f" ({', '.join(details)})" if details else ""
    logger.info("Étape « %s » : squelette I1, logique à venir%s.", step, suffix)


def step_scan(*, limit: int | None = None, dry_run: bool = False) -> int:
    """Étape ``scan`` — squelette (implémentée en I2)."""
    _log_stub("scan", limit, dry_run)
    return EXIT_OK


def step_archive(*, limit: int | None = None, dry_run: bool = False) -> int:
    """Étape ``archive`` — squelette (implémentée en I3)."""
    _log_stub("archive", limit, dry_run)
    return EXIT_OK


def step_transfer(*, dry_run: bool = False) -> int:
    """Étape ``transfer`` — squelette (implémentée en I4)."""
    _log_stub("transfer", None, dry_run)
    return EXIT_OK


def execute(command: str, *, limit: int | None, dry_run: bool) -> int:
    """Exécute la commande demandée et retourne un code retour.

    Le vidage final de ``backup/`` (``all``, ``cleanup``) n'est pas fait ici : il est
    garanti par :func:`main` dans son ``finally``, y compris en cas d'annulation.
    """
    if command == "scan":
        return step_scan(limit=limit, dry_run=dry_run)
    if command == "archive":
        if not dry_run:
            require_backup_dir()
        return step_archive(limit=limit, dry_run=dry_run)
    if command == "transfer":
        return step_transfer(dry_run=dry_run)
    if command == "cleanup":
        return EXIT_OK

    # all
    if not dry_run:
        require_backup_dir()
        logger.info("Vidage initial de backup/ : %d élément(s) supprimé(s).", empty_backup())
    return_code = step_scan(limit=limit, dry_run=dry_run)
    if return_code == EXIT_OK:
        return_code = step_archive(limit=limit, dry_run=dry_run)
    if return_code == EXIT_OK:
        return_code = step_transfer(dry_run=dry_run)
    return return_code


# --- Ligne de commande ------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments. Un argument invalide sort en ``EXIT_USAGE`` (2)."""
    parser = argparse.ArgumentParser(
        prog="databackup",
        description="DataBackup — sauvegarde chiffrée des documents vers Proton Drive.",
    )
    parser.set_defaults(command=None, dry_run=False, limit=None)
    subparsers = parser.add_subparsers(dest="command", metavar="{scan,archive,transfer,cleanup,all}")

    commands = (
        ("scan", "Recenser ce qui serait sauvegardé (sans rien écrire)"),
        ("archive", "Créer les archives chiffrées dans backup/"),
        ("transfer", "Envoyer les archives de backup/ vers Proton Drive"),
        ("cleanup", "Vider backup/"),
        ("all", "scan + archive + transfer puis vidage de backup/ (défaut)"),
    )
    for name, help_text in commands:
        subparser = subparsers.add_parser(name, help=help_text)
        subparser.add_argument(
            "--dry-run",
            action="store_true",
            help="Afficher le plan sans rien écrire dans backup/ ni rien envoyer.",
        )
        if name in ("scan", "archive", "all"):
            subparser.add_argument(
                "--limit",
                type=int,
                default=None,
                metavar="N",
                help="Ne traiter que les N premiers dossiers de premier niveau (test).",
            )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée. Retourne un code retour exploitable par ``start.sh`` / Piloter."""
    args = parse_args(argv)
    command = args.command or DEFAULT_COMMAND

    log_path = setup_logging()
    logger.info("=== DataBackup — %s ===", command)
    logger.info("Journal : %s", log_path)
    if args.dry_run:
        logger.info("Mode --dry-run : rien ne sera écrit dans backup/, rien ne sera envoyé.")
    if args.limit is not None:
        logger.info("Limite : %d dossier(s) de premier niveau.", args.limit)
    log_password_source()

    install_signal_handlers()
    try:
        acquire_lock()
    except LockError as exc:
        logger.error("%s", exc)
        remove_signal_handlers()
        return EXIT_LOCKED

    started = time.monotonic()
    try:
        return_code = execute(command, limit=args.limit, dry_run=args.dry_run)
    except BackupUnavailable as exc:
        logger.error("%s", exc)
        return_code = EXIT_BACKUP
    except Cancelled:
        logger.warning("Annulation demandée — arrêt propre.")
        return_code = EXIT_ERROR
    except Exception:
        logger.exception("Échec du traitement")
        return_code = EXIT_ERROR
    finally:
        remove_signal_handlers()
        if command in CLEANUP_COMMANDS and not args.dry_run and not _final_cleanup():
            return_code = EXIT_BACKUP
        release_lock()

    logger.info("Terminé en %s (code %d).", format_duration(time.monotonic() - started), return_code)
    return return_code


if __name__ == "__main__":
    sys.exit(main())

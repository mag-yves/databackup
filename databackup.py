#!/usr/bin/env python3
"""DataBackup — sauvegarde chiffrée des documents vers Proton Drive.

Étapes (cf. ``cdc.md`` §6 et §8) :

- ``scan`` : recense les dossiers de premier niveau et les fichiers racine à sauvegarder,
  en comparant chacun à l'historique (incrémental) ;
- ``archive`` : crée un zip chiffré AES-256 par dossier **nouveau ou modifié** dans ``backup/`` ;
- ``transfer`` : envoie les zips de ``backup/`` vers Proton Drive, puis inscrit dans
  l'historique les seules archives **réellement transférées** ;
- ``cleanup`` : vide ``backup/`` ;
- ``all`` : scan → archive → transfer, puis vidage de ``backup/`` (défaut).

**Sauvegarde incrémentale** (``cdc.md`` §6) : une archive est ignorée **uniquement** si sa
signature (chemins, tailles, dates de modification — sans lire le contenu) est identique à celle
d'un transfert réussi passé. Historique absent ou illisible, dossier renommé, ``--full`` : tout
est refait — perdre l'historique ne fait jamais manquer une sauvegarde.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from pathlib import Path

import pyzipper

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
UPLOAD_STRATEGY = "replace"

# Secret des archives : la variable d'environnement est prioritaire sur .env — cf. cdc.md §7.
PASSWORD_ENV_VAR = "DATABACKUP_ZIP_PASSWORD"

# Rotation des journaux : on ne conserve que les N derniers — cf. cdc.md §9.
LOG_KEEP = 7

# Sauvegarde incrémentale — cf. cdc.md §6.
STATE_FILE = PROJECT_DIR / ".databackup-state.json"  # historique (non versionné)
STATE_VERSION = 1
MANIFEST_NAME = ".databackup-manifest.json"  # manifeste du run, temporaire, dans backup/
STATUS_NEW = "nouveau"
STATUS_MODIFIED = "modifie"
STATUS_UNCHANGED = "inchange"

# Plage de dates représentable dans un zip (cf. cdc.md §6) : hors plage, la date est ramenée
# à 1980 pour ne pas perdre le fichier.
ZIP_MIN_YEAR = 1980
ZIP_MAX_YEAR = 2107

# Extensions déjà compressées : stockées sans compression (mais toujours chiffrées),
# liste figée du CDC §4.
STORED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".mp4", ".stl", ".3mf", ".zip"})

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


class ScanError(RuntimeError):
    """Scan impossible (source absente, collision de noms d'archives) — cf. cdc.md §3, §4."""


# --- Utilitaires ------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Formate une durée en ``H:MM:SS``."""
    total = round(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}"


def format_size(num_bytes: int) -> str:
    """Formate une taille en octets de façon lisible (o, Ko, Mo, Go)."""
    size = float(num_bytes)
    for unit in ("o", "Ko", "Mo"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.2f} Go"


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


# --- Historique des sauvegardes (incrémental) -------------------------------


@dataclass(frozen=True)
class ArchiveRecord:
    """Ce qu'un transfert réussi a réellement envoyé, et quand (cf. cdc.md §6).

    ``signature`` est l'empreinte de l'arborescence source **au moment de l'archivage**
    (cf. :func:`archive_signature`) ; les autres champs sont indicatifs (affichage, diagnostic).
    """

    signature: str
    files: int = 0
    source_bytes: int = 0
    archive_bytes: int = 0
    last_backup: str = ""


def _file_fingerprint(path: Path) -> str:
    """Empreinte bon marché d'un fichier : ``taille:date_mtime_ns`` (``?`` si illisible)."""
    try:
        info = path.stat()
    except OSError:
        return "?"
    return f"{info.st_size}:{info.st_mtime_ns}"


def archive_signature(files: list[Path], empty_dirs: list[Path], base: Path) -> str:
    """Empreinte de l'arborescence à sauvegarder — base de l'incrémental (cf. cdc.md §6).

    Le **contenu n'est pas lu** : l'empreinte combine le chemin relatif, la taille et la date de
    modification (ns) de chaque fichier, plus les sous-dossiers vides. Deux états identiques
    donnent la même empreinte ; toute modification visible par ces métadonnées en donne une autre.
    """
    lines = [f"{path.relative_to(base).as_posix()}:{_file_fingerprint(path)}" for path in files]
    lines += [f"{path.relative_to(base).as_posix()}/:" for path in empty_dirs]
    digest = hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def archive_status(
    archive_name: str,
    signature: str,
    known: Mapping[str, ArchiveRecord],
    *,
    full: bool = False,
) -> tuple[str, str | None]:
    """Statut d'une archive face à l'historique : ``nouveau``, ``modifie`` ou ``inchange``.

    Retourne ``(statut, date du dernier transfert réussi)``. Aucune entrée d'historique → la
    sauvegarde est **incluse** (``nouveau``) : c'est le défaut sûr (cf. cdc.md §6). ``full=True``
    ignore l'historique pour la décision (tout est retenu), la date restant affichée.
    """
    record = known.get(archive_name)
    if record is None:
        return STATUS_NEW, None
    if full:
        return STATUS_MODIFIED, record.last_backup
    if record.signature == signature:
        return STATUS_UNCHANGED, record.last_backup
    return STATUS_MODIFIED, record.last_backup


def load_records(path: Path, label: str) -> dict[str, ArchiveRecord]:
    """Lit un fichier JSON ``{"archives": {nom: entrée}}`` (historique ou manifeste).

    Fichier absent → dictionnaire vide. Fichier **illisible ou incohérent** : avertissement et
    dictionnaire vide — le run ne doit **jamais** échouer pour un état de travers, et le défaut
    sûr reste la sauvegarde complète (cf. cdc.md §6).
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        archives = payload["archives"]
        if not isinstance(archives, dict):
            raise ValueError("clé « archives » invalide")
        records: dict[str, ArchiveRecord] = {}
        for name, entry in archives.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("signature"), str):
                raise ValueError(f"entrée invalide pour {name}")
            records[name] = ArchiveRecord(
                signature=entry["signature"],
                files=int(entry.get("files", 0)),
                source_bytes=int(entry.get("source_bytes", 0)),
                archive_bytes=int(entry.get("archive_bytes", 0)),
                last_backup=str(entry.get("last_backup", "")),
            )
        return records
    except (OSError, KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "%s illisible (%s) : %s — toutes les archives seront refaites.",
            label.capitalize(),
            path.name,
            exc,
        )
        return {}


def save_records(path: Path, records: Mapping[str, ArchiveRecord]) -> bool:
    """Écrit un fichier d'état de façon **atomique** (fichier temporaire puis remplacement).

    Retourne ``False`` si l'écriture est impossible : le run continue, et la prochaine exécution
    refera simplement tout (cf. cdc.md §6) — jamais d'échec silencieux, jamais de données perdues.
    """
    payload = {
        "version": STATE_VERSION,
        "archives": {name: asdict(record) for name, record in sorted(records.items())},
    }
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    except OSError as exc:
        logger.error("Écriture impossible (%s) : %s — la prochaine exécution refera tout.", path.name, exc)
        temporary.unlink(missing_ok=True)
        return False
    return True


def load_state(path: Path | None = None) -> dict[str, ArchiveRecord]:
    """Historique des sauvegardes réussies (cf. cdc.md §6)."""
    return load_records(path or STATE_FILE, "historique")


def save_state(records: Mapping[str, ArchiveRecord], path: Path | None = None) -> bool:
    """Enregistre l'historique — appelé **uniquement après un upload réussi** (cf. cdc.md §6)."""
    return save_records(path or STATE_FILE, records)


def manifest_path() -> Path:
    """Manifeste du run en cours : signatures des archives présentes dans ``backup/``."""
    return BACKUP_DIR / MANIFEST_NAME


def load_manifest() -> dict[str, ArchiveRecord]:
    """Signatures des archives réellement créées par ``archive`` (cf. cdc.md §6)."""
    return load_records(manifest_path(), "manifeste")


def save_manifest(records: Mapping[str, ArchiveRecord]) -> bool:
    """Écrit le manifeste des archives créées dans ``backup/`` (fichier temporaire)."""
    return save_records(manifest_path(), records)


# --- Scan des sources -------------------------------------------------------


def normalize_archive_name(folder_name: str) -> str:
    """Normalise un nom de dossier en base de nom d'archive (cf. cdc.md §4).

    Accents supprimés (NFKD), passage en minuscules, tout groupe de caractères hors
    ``a-z0-9`` remplacé par un tiret, tirets de bord retirés. Le suffixe ``.zip`` n'est
    pas ajouté (il l'est à la construction du plan).
    """
    decomposed = unicodedata.normalize("NFKD", folder_name)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", without_accents.lower()).strip("-")


@dataclass(frozen=True)
class ArchivePlan:
    """Archive prévue par le scan : nom cible, origine, contenu estimé, statut incrémental."""

    archive_name: str
    origin: Path
    label: str
    file_count: int
    total_size: int
    is_root_files: bool = False
    signature: str = ""
    status: str = STATUS_NEW
    last_backup: str | None = None


@dataclass(frozen=True)
class ScanReport:
    """Résultat d'un scan : archives retenues, ignorées (déjà à jour), vides, liens."""

    plans: list[ArchivePlan]
    excluded: list[Path]
    symlinks: list[Path]
    unchanged: list[ArchivePlan] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(plan.total_size for plan in self.plans)


def collect_folder_files(folder: Path) -> tuple[list[Path], list[Path]]:
    """Parcourt ``folder`` récursivement **sans suivre** les liens symboliques.

    Retourne ``(fichiers réguliers, liens symboliques)``, triés. Les sous-dossiers vides
    sont ignorés (aucune archive n'est créée pour eux à ce stade) ; les liens symboliques
    ne sont jamais suivis (évite les boucles et les sorties de périmètre — cdc.md §3).
    """
    files: list[Path] = []
    symlinks: list[Path] = []
    for current, dirnames, filenames in os.walk(folder, followlinks=False):
        current_path = Path(current)
        kept_dirs = []
        for dirname in dirnames:
            child = current_path / dirname
            if child.is_symlink():
                symlinks.append(child)
            else:
                kept_dirs.append(dirname)
        dirnames[:] = sorted(kept_dirs)
        for filename in filenames:
            child = current_path / filename
            if child.is_symlink():
                symlinks.append(child)
            elif child.is_file():
                files.append(child)
    return sorted(files), sorted(symlinks)


def _measure_files(files: list[Path]) -> int:
    """Somme des tailles, en avertissant pour tout fichier illisible (sans interrompre)."""
    total = 0
    for path in files:
        try:
            total += path.stat().st_size
        except OSError as exc:
            logger.warning("Fichier illisible, ignoré dans l'estimation : %s (%s)", path, exc)
    return total


def _check_archive_conflicts(plans: list[ArchivePlan]) -> None:
    """Échoue si deux archives visent le même nom, ou si un nom normalisé est vide (§4)."""
    labels_by_name: dict[str, list[str]] = {}
    for plan in plans:
        labels_by_name.setdefault(plan.archive_name, []).append(plan.label)

    conflicts = [f"{name} : {', '.join(labels)}" for name, labels in sorted(labels_by_name.items()) if len(labels) > 1]
    if conflicts:
        raise ScanError("Collision de noms d'archives — " + " ; ".join(conflicts))

    empty_names = [plan.label for plan in plans if plan.archive_name == ".zip"]
    if empty_names:
        raise ScanError("Nom d'archive impossible (nom normalisé vide) pour : " + ", ".join(empty_names))


def plan_archives(
    source_dir: Path | None = None,
    limit: int | None = None,
    *,
    state: Mapping[str, ArchiveRecord] | None = None,
    full: bool = False,
) -> ScanReport:
    """Construit le plan de sauvegarde à partir de ``source_dir`` (cf. cdc.md §3, §4, §6).

    Un dossier de premier niveau = une archive récursive ; les fichiers placés directement à la
    racine vont dans ``documents.zip``. Un dossier vide est exclu. ``limit`` ne retient que les N
    premiers dossiers **retenus** (les fichiers racine restent inclus).

    **Incrémental** : chaque archive est comparée à l'historique ``state`` par sa signature
    (:func:`archive_signature`) ; seules les archives **nouvelles ou modifiées** entrent dans
    ``plans``, les autres vont dans ``ScanReport.unchanged``. ``full=True`` ignore l'historique
    pour la décision. Lève :class:`ScanError` si la source est absente ou si des noms d'archives
    se recouvrent — la vérification des collisions porte sur **toutes** les archives, y compris
    celles ignorées.
    """
    source = source_dir or SOURCE_DIR
    if not source.is_dir():
        raise ScanError(f"Dossier source introuvable : {source} — le symlink source/ est-il en place ?")

    known = load_state() if state is None else state

    folder_plans: list[ArchivePlan] = []
    excluded: list[Path] = []
    symlinks: list[Path] = []
    root_files: list[Path] = []

    for entry in sorted(source.iterdir(), key=lambda path: path.name):
        if entry.is_symlink():
            symlinks.append(entry)
        elif entry.is_file():
            root_files.append(entry)
        elif entry.is_dir():
            files, links = collect_folder_files(entry)
            symlinks.extend(links)
            if not files:
                excluded.append(entry)
                continue
            archive_name = f"{normalize_archive_name(entry.name)}.zip"
            signature = archive_signature(files, collect_empty_dirs(entry), entry)
            status, last_backup = archive_status(archive_name, signature, known, full=full)
            folder_plans.append(
                ArchivePlan(
                    archive_name=archive_name,
                    origin=entry,
                    label=entry.name,
                    file_count=len(files),
                    total_size=_measure_files(files),
                    signature=signature,
                    status=status,
                    last_backup=last_backup,
                )
            )

    root_plan: ArchivePlan | None = None
    if root_files:
        signature = archive_signature(root_files, [], source)
        status, last_backup = archive_status("documents.zip", signature, known, full=full)
        root_plan = ArchivePlan(
            archive_name="documents.zip",
            origin=source,
            label="fichiers racine",
            file_count=len(root_files),
            total_size=_measure_files(root_files),
            signature=signature,
            status=status,
            last_backup=last_backup,
            is_root_files=True,
        )

    # Toutes les archives sont contrôlées (y compris les inchangées et celles écartées par
    # ``limit``) : une collision doit toujours arrêter le scan (cf. cdc.md §4).
    _check_archive_conflicts([*folder_plans, *([root_plan] if root_plan else [])])

    retained = [plan for plan in folder_plans if plan.status != STATUS_UNCHANGED]
    unchanged = [plan for plan in folder_plans if plan.status == STATUS_UNCHANGED]
    if limit is not None:
        retained = retained[:limit]

    plans = list(retained)
    if root_plan is not None:
        if root_plan.status == STATUS_UNCHANGED:
            unchanged.append(root_plan)
        else:
            plans.append(root_plan)
    return ScanReport(plans=plans, excluded=excluded, symlinks=symlinks, unchanged=unchanged)


def _log_scan(report: ScanReport, dry_run: bool) -> None:
    for symlink in report.symlinks:
        logger.warning("Lien symbolique ignoré : %s", symlink)
    for folder in report.excluded:
        logger.info("Dossier de premier niveau vide, exclu : %s", folder.name)

    for plan in report.unchanged:
        since = f", sauvegardé le {plan.last_backup}" if plan.last_backup else ""
        logger.info("[inchangé] %s -> %s (déjà à jour%s)", plan.label, plan.archive_name, since)

    total = len(report.plans)
    new = sum(1 for plan in report.plans if plan.status == STATUS_NEW)
    logger.info(
        "%d archive(s) à faire (%d nouvelle(s), %d modifiée(s)) ; %d ignorée(s) (inchangée(s)) ; "
        "%d dossier(s) vide(s) exclu(s).",
        total,
        new,
        total - new,
        len(report.unchanged),
        len(report.excluded),
    )
    for index, plan in enumerate(report.plans, 1):
        logger.info(
            "[%d/%d] (%s) %s -> %s (%d fichier(s), %s)",
            index,
            total,
            plan.status,
            plan.label,
            plan.archive_name,
            plan.file_count,
            format_size(plan.total_size),
        )
    logger.info("Volume estimé : %s.", format_size(report.total_size))
    if dry_run:
        logger.info("Cible : %s (aucun envoi en --dry-run).", PROTON_PARENT)


# --- Création des archives --------------------------------------------------


def _compress_type(path: Path) -> int:
    """Compression d'un fichier : stocké si le format est déjà compressé, sinon dégonflé (§4)."""
    return pyzipper.ZIP_STORED if path.suffix.lower() in STORED_EXTENSIONS else pyzipper.ZIP_DEFLATED


def collect_root_files(source: Path) -> list[Path]:
    """Fichiers posés directement à la racine de ``source`` (liens symboliques exclus)."""
    return sorted(entry for entry in source.iterdir() if not entry.is_symlink() and entry.is_file())


def collect_empty_dirs(folder: Path) -> list[Path]:
    """Sous-dossiers vides de ``folder`` (aucun fichier dans leur sous-arbre).

    Conservés dans l'archive pour restituer fidèlement l'arborescence (cf. cdc.md §3).
    """
    non_empty: set[Path] = set()
    empty: list[Path] = []
    for current, dirnames, filenames in os.walk(folder, topdown=False, followlinks=False):
        path = Path(current)
        if path == folder:
            continue
        has_file = any(not (path / name).is_symlink() and (path / name).is_file() for name in filenames)
        has_content = has_file or any((path / name) in non_empty for name in dirnames)
        if has_content:
            non_empty.add(path)
        else:
            empty.append(path)
    return sorted(empty)


@dataclass(frozen=True)
class ArchiveStats:
    """Ce qui a réellement été écrit dans une archive."""

    file_count: int
    empty_dirs: int
    size: int


def modification_year(path: Path) -> int | None:
    """Année de dernière modification, ou ``None`` si le fichier est disparu ou illisible.

    Une date inexploitable (valeur aberrante) est signalée par ``0`` : elle est traitée comme
    hors plage, mais le fichier reste archivé (cf. cdc.md §6).
    """
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).year
    except OSError:
        return None
    except (OverflowError, ValueError):
        return 0


def write_archive(plan: ArchivePlan, destination: Path, password: str) -> ArchiveStats:
    """Écrit l'archive chiffrée AES-256 de ``plan`` dans ``destination`` (cf. cdc.md §4).

    L'arborescence interne est préservée (chemins relatifs à l'origine) et les sous-dossiers
    vides sont conservés. Un fichier disparu, illisible, ou que le format refuse est **signalé
    et ignoré** sans interrompre le reste ; une date de modification hors plage ZIP (avant 1980
    ou après 2107) est **ramenée à 1980** pour ne pas perdre le fichier (cf. cdc.md §6).
    """
    base = plan.origin
    if plan.is_root_files:
        files = collect_root_files(base)
        empty_dirs: list[Path] = []
    else:
        files, _symlinks = collect_folder_files(base)
        empty_dirs = collect_empty_dirs(base)

    written = 0
    with pyzipper.AESZipFile(
        destination,
        "w",
        compression=pyzipper.ZIP_DEFLATED,
        encryption=pyzipper.WZ_AES,
        strict_timestamps=False,  # date hors plage : ramenée à 1980 au lieu de lever une erreur
    ) as archive:
        archive.setpassword(password.encode("utf-8"))
        for empty_dir in empty_dirs:
            archive.writestr(f"{empty_dir.relative_to(base).as_posix()}/", b"")
        for file in files:
            year = modification_year(file)
            if year is None:
                logger.warning("Fichier disparu ou illisible pendant l'archivage, ignoré : %s", file)
                continue
            if not ZIP_MIN_YEAR <= year <= ZIP_MAX_YEAR:
                logger.warning("Date de modification hors plage ZIP (ramenée à %d) : %s", ZIP_MIN_YEAR, file)
            try:
                archive.write(
                    file,
                    arcname=file.relative_to(base).as_posix(),
                    compress_type=_compress_type(file),
                )
            except (OSError, ValueError) as exc:
                logger.warning("Fichier non archivé, ignoré : %s (%s)", file, exc)
                continue
            written += 1

    return ArchiveStats(file_count=written, empty_dirs=len(empty_dirs), size=destination.stat().st_size)


# --- Transfert vers Proton Drive --------------------------------------------


def is_interactive() -> bool:
    """Indique si l'exécution se fait dans un vrai terminal (requis par ``auth login``)."""
    return sys.stdin.isatty()


def run_proton_drive(args: list[str]) -> tuple[int, str]:
    """Exécute le CLI ``proton-drive`` en capturant sa sortie. Retourne (code retour, sortie)."""
    result = subprocess.run([str(PROTON_DRIVE), *args], capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def proton_login() -> bool:
    """Lance ``auth login`` (interactif : navigateur). Retourne ``True`` si succès."""
    logger.info("Authentification Proton Drive — ouverture de `auth login` ...")
    return subprocess.run([str(PROTON_DRIVE), "auth", "login"]).returncode == 0


def upload_archive(archive: Path) -> bool:
    """Envoie une archive vers Proton Drive (``upload -f replace``) — cf. cdc.md §5."""
    code, output = run_proton_drive(["filesystem", "upload", "-f", UPLOAD_STRATEGY, str(archive), PROTON_PARENT])
    for line in output.splitlines():
        if line.strip():
            logger.info("    | %s", line.strip())
    if code != 0:
        logger.error("Échec de l'upload de %s (code %s).", archive.name, code)
        return False
    return True


# --- Récapitulatif et étapes -------------------------------------------------


@dataclass
class RunStats:
    """Compteurs consolidés d'un run, pour le récapitulatif final (cf. cdc.md §9)."""

    archives_planned: int = 0
    archives_unchanged: int = 0
    archives_created: int = 0
    archive_volume: int = 0
    archives_sent: int = 0
    transfer_failures: int = 0


def step_scan(
    *, limit: int | None = None, dry_run: bool = False, full: bool = False, stats: RunStats | None = None
) -> int:
    """Étape ``scan`` : affiche le plan de sauvegarde, sans rien écrire ni envoyer."""
    try:
        report = plan_archives(limit=limit, full=full)
    except ScanError as exc:
        logger.error("%s", exc)
        return EXIT_ERROR
    if stats is not None:
        stats.archives_planned = len(report.plans)
        stats.archives_unchanged = len(report.unchanged)
    _log_scan(report, dry_run)
    return EXIT_OK


def step_archive(
    *, limit: int | None = None, dry_run: bool = False, full: bool = False, stats: RunStats | None = None
) -> int:
    """Étape ``archive`` : crée les zips chiffrés dans ``backup/`` (cf. cdc.md §4).

    Seules les archives **nouvelles ou modifiées** sont créées (cf. cdc.md §6) ; les signatures
    de celles réellement écrites partent dans le **manifeste** du run, que ``transfer`` lira
    pour l'historique.
    """
    try:
        report = plan_archives(limit=limit, full=full)
    except ScanError as exc:
        logger.error("%s", exc)
        return EXIT_ERROR

    if stats is not None:
        stats.archives_planned = len(report.plans)
        stats.archives_unchanged = len(report.unchanged)

    if dry_run:
        logger.info("--dry-run : %d archive(s) seraient créées dans %s.", len(report.plans), BACKUP_DIR)
        return EXIT_OK

    if not report.plans:
        logger.info("Aucune archive à créer : tous les dossiers sont déjà à jour (cf. cdc.md §6).")
        return EXIT_OK

    password = resolve_password()
    if not password:
        logger.error(
            "Mot de passe des archives introuvable (ni %s, ni %s) — archivage impossible.",
            PASSWORD_ENV_VAR,
            ENV_FILE.name,
        )
        return EXIT_ERROR

    total = len(report.plans)
    logger.info("%d archive(s) à créer dans %s.", total, BACKUP_DIR)
    volume = 0
    errors = 0
    manifest: dict[str, ArchiveRecord] = {}
    for index, plan in enumerate(report.plans, 1):
        logger.info("[%d/%d] %s -> %s ...", index, total, plan.label, plan.archive_name)
        started = time.monotonic()
        try:
            archive_stats = write_archive(plan, BACKUP_DIR / plan.archive_name, password)
        except OSError as exc:
            errors += 1
            logger.error("[%d/%d] [ERREUR] %s : %s", index, total, plan.archive_name, exc)
            continue
        manifest[plan.archive_name] = ArchiveRecord(
            signature=plan.signature,
            files=archive_stats.file_count,
            source_bytes=plan.total_size,
            archive_bytes=archive_stats.size,
        )
        volume += archive_stats.size
        if stats is not None:
            stats.archives_created += 1
            stats.archive_volume = volume
        logger.info(
            "[%d/%d] OK %s (%d fichier(s), %d dossier(s) vide(s), %s, %s)",
            index,
            total,
            plan.archive_name,
            archive_stats.file_count,
            archive_stats.empty_dirs,
            format_size(archive_stats.size),
            format_duration(time.monotonic() - started),
        )

    if manifest:
        save_manifest(manifest)

    logger.info(
        "Archivage terminé : %d/%d archive(s), %s, %d erreur(s).",
        total - errors,
        total,
        format_size(volume),
        errors,
    )
    return EXIT_ERROR if errors else EXIT_OK


def step_transfer(*, dry_run: bool = False, stats: RunStats | None = None) -> int:
    """Étape ``transfer`` : envoie les archives vers Proton Drive (cf. cdc.md §5, §6).

    Un échec est **compté** et le run continue ; dans un terminal, une **unique** tentative
    d'``auth login`` (navigateur) suivie de la reprise de l'archive en cours est permise. Hors
    terminal, un échec stoppe avec le code `4` (« lancez ``./proton-drive auth login`` »).
    """
    archives = sorted(BACKUP_DIR.glob("*.zip"))
    if dry_run:
        logger.info("--dry-run : %d archive(s) seraient envoyées vers %s.", len(archives), PROTON_PARENT)
        return EXIT_OK
    if not archives:
        logger.warning("Aucune archive à transférer dans %s.", BACKUP_DIR)
        return EXIT_OK
    if not PROTON_DRIVE.is_file() or not os.access(PROTON_DRIVE, os.X_OK):
        logger.error("Binaire proton-drive introuvable ou non exécutable (%s) — lancez ./install.sh.", PROTON_DRIVE)
        return EXIT_ERROR

    total = len(archives)
    logger.info("Transfert de %d archive(s) vers %s ...", total, PROTON_PARENT)
    failures = 0
    login_attempted = False
    sent: list[Path] = []
    for index, archive in enumerate(archives, 1):
        logger.info("[%d/%d] upload de %s (%s) ...", index, total, archive.name, format_size(archive.stat().st_size))
        started = time.monotonic()
        ok = upload_archive(archive)

        if not ok and not is_interactive():
            if stats is not None:
                stats.transfer_failures += 1
            logger.error(
                "Échec hors terminal : `auth login` est impossible. Lancez `./proton-drive auth login` "
                "dans un terminal, puis relancez.",
            )
            _record_backups(sent)
            return EXIT_AUTH
        if not ok and not login_attempted:
            login_attempted = True
            if proton_login():
                logger.info("Reconnexion réussie — reprise de %s.", archive.name)
                ok = upload_archive(archive)

        if ok:
            sent.append(archive)
            logger.info(
                "[%d/%d] OK %s transférée (%s).",
                index,
                total,
                archive.name,
                format_duration(time.monotonic() - started),
            )
        else:
            failures += 1
            logger.error("[%d/%d] ÉCHEC %s — compté, le run continue.", index, total, archive.name)

    if stats is not None:
        stats.archives_sent = total - failures
        stats.transfer_failures = failures

    _record_backups(sent)

    if failures:
        logger.error("Transfert terminé : %d/%d archive(s), %d échec(s).", total - failures, total, failures)
        return EXIT_ERROR
    logger.info("Transfert terminé : %d/%d archive(s).", total, total)
    return EXIT_OK


def _record_backups(sent: list[Path]) -> None:
    """Inscrit dans l'historique les archives **réellement transférées** (cf. cdc.md §6).

    Les signatures viennent du **manifeste** écrit par ``archive`` : c'est l'état de la source au
    moment de l'archivage, donc le contenu réellement présent sur Proton — et non l'état de
    ``source/`` au moment du transfert (kDrive peut avoir bougé entre-temps). Sans manifeste,
    rien n'est inscrit : le défaut reste sûr, la prochaine exécution refera tout.
    """
    if not sent:
        return
    manifest = load_manifest()
    missing = [archive.name for archive in sent if archive.name not in manifest]
    if missing:
        logger.warning(
            "Manifeste absent pour %d archive(s) (%s) : historique non mis à jour, elles seront refaites "
            "au prochain run. Enchaînez `archive` puis `transfer` dans la même exécution (ou `all`).",
            len(missing),
            ", ".join(missing),
        )
    records = load_state()
    now = datetime.now().isoformat(timespec="seconds")
    updated = 0
    for archive in sent:
        entry = manifest.get(archive.name)
        if entry is None:
            continue
        records[archive.name] = replace(entry, last_backup=now)
        updated += 1
    if updated and save_state(records):
        logger.info("Historique mis à jour : %d archive(s) à jour au %s.", updated, now)


def execute(command: str, *, limit: int | None, dry_run: bool, full: bool, stats: RunStats) -> int:
    """Exécute la commande demandée et retourne un code retour.

    ``all`` et ``archive`` vident ``backup/`` au début (cf. cdc.md §6, étape 2). Le vidage
    final (``all``, ``cleanup``) est garanti par :func:`main` dans son ``finally``, y compris
    en cas d'annulation. ``stats`` est alimenté pour le récapitulatif final. ``full`` ignore
    l'historique (tout est refait) — cf. cdc.md §6.
    """
    if command == "scan":
        return step_scan(limit=limit, dry_run=dry_run, full=full, stats=stats)
    if command == "cleanup":
        return EXIT_OK

    # all / archive / transfer — dossier temporaire requis (cf. cdc.md §6, étape 1)
    if not dry_run:
        require_backup_dir()

    if command == "transfer":
        return step_transfer(dry_run=dry_run, stats=stats)

    # archive / all — vidage initial avant tout traitement
    if not dry_run:
        logger.info("Vidage initial de backup/ : %d élément(s) supprimé(s).", empty_backup())

    if command == "archive":
        return step_archive(limit=limit, dry_run=dry_run, full=full, stats=stats)

    return_code = step_scan(limit=limit, dry_run=dry_run, full=full, stats=stats)
    if return_code == EXIT_OK:
        return_code = step_archive(limit=limit, dry_run=dry_run, full=full, stats=stats)
    if return_code == EXIT_OK:
        return_code = step_transfer(dry_run=dry_run, stats=stats)
    return return_code


def _log_summary(stats: RunStats, elapsed: float, return_code: int, *, dry_run: bool) -> None:
    """Récapitulatif final, affiché et journalisé (cf. cdc.md §9)."""
    if not dry_run:
        logger.info("=== Récapitulatif ===")
        logger.info(
            "Archives : %d prévue(s), %d créée(s) (%s), %d envoyée(s), %d échec(s) de transfert.",
            stats.archives_planned,
            stats.archives_created,
            format_size(stats.archive_volume),
            stats.archives_sent,
            stats.transfer_failures,
        )
        if stats.archives_unchanged:
            logger.info("Archives ignorées (déjà à jour) : %d.", stats.archives_unchanged)
    logger.info("Durée : %s. Code retour : %d.", format_duration(elapsed), return_code)


# --- Ligne de commande ------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Analyse les arguments. Un argument invalide sort en ``EXIT_USAGE`` (2)."""
    parser = argparse.ArgumentParser(
        prog="databackup",
        description="DataBackup — sauvegarde chiffrée des documents vers Proton Drive.",
    )
    parser.set_defaults(command=None, dry_run=False, limit=None, full=False)
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
            subparser.add_argument(
                "--full",
                action="store_true",
                help="Ignorer l'historique : refaire toutes les archives (sauvegarde complète).",
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
    if args.full:
        logger.info("Option --full : l'historique est ignoré, toutes les archives sont refaites.")
    if command in ("all", "archive"):
        log_password_source()

    install_signal_handlers()
    try:
        acquire_lock()
    except LockError as exc:
        logger.error("%s", exc)
        remove_signal_handlers()
        return EXIT_LOCKED

    started = time.monotonic()
    stats = RunStats()
    try:
        return_code = execute(command, limit=args.limit, dry_run=args.dry_run, full=args.full, stats=stats)
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

    _log_summary(stats, time.monotonic() - started, return_code, dry_run=args.dry_run)
    return return_code


if __name__ == "__main__":
    sys.exit(main())

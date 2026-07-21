from __future__ import annotations

from pathlib import Path


DATA_ROOT = Path(".data")

USER_DATA_ROOT = DATA_ROOT / "user"
USER_CONFIG_DIR = USER_DATA_ROOT / "config"
LLM_CONFIG_DIR = USER_CONFIG_DIR / "llm"
STUDIO_CONFIG_DIR = USER_CONFIG_DIR / "studio"
LLM_PROVIDERS_FILE = LLM_CONFIG_DIR / "providers.json"
LLM_ASSIGNMENTS_FILE = LLM_CONFIG_DIR / "assignments.json"
STUDIO_CREDENTIALS_FILE = STUDIO_CONFIG_DIR / "credentials.json"
STUDIO_RESOURCES_FILE = STUDIO_CONFIG_DIR / "resources.json"
DEV_CARTRIDGES_DIR = USER_DATA_ROOT / "dev_cartridges"
INSTALLED_CARTRIDGES_DIR = USER_DATA_ROOT / "installed_cartridges"
PACKAGES_DIR = USER_DATA_ROOT / "packages"
ARTIFACTS_DIR = USER_DATA_ROOT / "artifacts"
CARTRIDGE_DATA_DIR = USER_DATA_ROOT / "cartridge_data"

RUNTIME_DATA_ROOT = DATA_ROOT / "runtime"
RUNS_DIR = RUNTIME_DATA_ROOT / "runs"
WORKERS_DIR = RUNTIME_DATA_ROOT / "workers"

REPORTS_DATA_ROOT = DATA_ROOT / "reports"
LOGS_DIR = REPORTS_DATA_ROOT / "logs"
CONFORMANCE_DIR = REPORTS_DATA_ROOT / "conformance"
CONFORMANCE_REPORT = CONFORMANCE_DIR / "latest.json"
ERROR_REPORTS_DIR = REPORTS_DATA_ROOT / "errors"

TEMP_DATA_ROOT = DATA_ROOT / "temp"
UPLOADS_DIR = TEMP_DATA_ROOT / "uploads"
IMPORTS_DIR = TEMP_DATA_ROOT / "imports"


LEGACY_DIRECTORY_MOVES = (
    (DATA_ROOT / "dev_cartridges", DEV_CARTRIDGES_DIR),
    (DATA_ROOT / "installed_cartridges", INSTALLED_CARTRIDGES_DIR),
    (DATA_ROOT / "cartridge_packages", PACKAGES_DIR),
    (DATA_ROOT / "cartridge_dlc", CARTRIDGE_DATA_DIR),
    (DATA_ROOT / "cartridge_runs", RUNS_DIR),
    (DATA_ROOT / "runtime_workers", WORKERS_DIR),
    (DATA_ROOT / "diagnostics", REPORTS_DATA_ROOT),
    (DATA_ROOT / "logs", LOGS_DIR),
    (DATA_ROOT / "conformance", CONFORMANCE_DIR),
    (DATA_ROOT / "uploads", UPLOADS_DIR),
    (DATA_ROOT / "tmp_imports", IMPORTS_DIR),
)

LEGACY_FILE_MOVES = (
    (Path("config/llm/providers.json"), LLM_PROVIDERS_FILE),
    (Path("config/llm/assignments.json"), LLM_ASSIGNMENTS_FILE),
    (Path("config/studio/credentials.json"), STUDIO_CREDENTIALS_FILE),
    (Path("config/studio/resources.json"), STUDIO_RESOURCES_FILE),
)

CANONICAL_DIRECTORIES = (
    LLM_CONFIG_DIR,
    STUDIO_CONFIG_DIR,
    DEV_CARTRIDGES_DIR,
    INSTALLED_CARTRIDGES_DIR,
    PACKAGES_DIR,
    ARTIFACTS_DIR,
    CARTRIDGE_DATA_DIR,
    RUNS_DIR,
    WORKERS_DIR,
    LOGS_DIR,
    CONFORMANCE_DIR,
    ERROR_REPORTS_DIR,
    UPLOADS_DIR,
    IMPORTS_DIR,
)


class DataLayoutMigrationError(RuntimeError):
    pass


def ensure_data_layout(root: str | Path) -> list[dict[str, str]]:
    base = Path(root).resolve()
    migrations = []
    for legacy_relative, target_relative in LEGACY_FILE_MOVES:
        source = base / legacy_relative
        target = base / target_relative
        if not source.exists():
            continue
        if not source.is_file():
            raise DataLayoutMigrationError(f"Cannot migrate {legacy_relative.as_posix()}: source is not a file")
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not target.is_file() or source.read_bytes() != target.read_bytes():
                raise DataLayoutMigrationError(
                    f"Cannot migrate {legacy_relative.as_posix()}: target already contains different data"
                )
            source.unlink()
        else:
            source.replace(target)
        migrations.append({"from": legacy_relative.as_posix(), "to": target_relative.as_posix()})

    for legacy_relative, target_relative in LEGACY_DIRECTORY_MOVES:
        source = base / legacy_relative
        target = base / target_relative
        if not source.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            conflicts = _directory_conflicts(source, target)
            if conflicts:
                joined = ", ".join(conflicts[:5])
                raise DataLayoutMigrationError(
                    f"Cannot migrate {legacy_relative.as_posix()}: target conflicts at {joined}"
                )
            _merge_directories(source, target)
        else:
            source.replace(target)
        migrations.append({"from": legacy_relative.as_posix(), "to": target_relative.as_posix()})

    for relative in CANONICAL_DIRECTORIES:
        (base / relative).mkdir(parents=True, exist_ok=True)
    return migrations


def _directory_conflicts(source: Path, target: Path) -> list[str]:
    if not source.is_dir() or not target.is_dir():
        return [target.name]
    conflicts = []
    for item in source.iterdir():
        destination = target / item.name
        if not destination.exists():
            continue
        if item.is_dir() and destination.is_dir():
            conflicts.extend(f"{item.name}/{value}" for value in _directory_conflicts(item, destination))
        else:
            conflicts.append(item.name)
    return conflicts


def _merge_directories(source: Path, target: Path) -> None:
    for item in list(source.iterdir()):
        destination = target / item.name
        if item.is_dir() and destination.is_dir():
            _merge_directories(item, destination)
        else:
            item.replace(destination)
    source.rmdir()

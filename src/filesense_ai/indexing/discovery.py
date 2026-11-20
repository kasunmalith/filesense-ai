from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from filesense_ai.core.paths import normalized_path

SUPPORTED = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".csv",
    ".log",
    ".xlsx",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
DEFAULT_EXCLUDES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "$recycle.bin",
    "system volume information",
}


@dataclass(frozen=True)
class DiscoveredFile:
    path: Path
    size: int
    mtime_ns: int


@dataclass
class ScanResult:
    files: list[DiscoveredFile]
    complete: bool
    errors: int = 0


def discover(
    root: Path,
    max_file_size: int,
    excludes: set[str] | None = None,
    excluded_paths: set[Path] | None = None,
) -> ScanResult:
    excluded = {p.casefold() for p in (excludes or DEFAULT_EXCLUDES)}
    protected = {normalized_path(path).rstrip("\\/") for path in (excluded_paths or set())}

    def is_protected(path: Path) -> bool:
        candidate = normalized_path(path)
        return any(
            candidate == value or candidate.startswith(value + os.sep) for value in protected
        )

    if is_protected(root):
        return ScanResult([], False, 1)
    results: list[DiscoveredFile] = []
    stack = [root]
    complete = True
    errors = 0
    while stack:
        folder = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    name = entry.name.casefold()
                    if name in excluded or name.startswith("~$"):
                        continue
                    if is_protected(Path(entry.path)):
                        continue
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif (
                            entry.is_file(follow_symlinks=False) and Path(name).suffix in SUPPORTED
                        ):
                            stat = entry.stat(follow_symlinks=False)
                            if stat.st_size <= max_file_size:
                                results.append(
                                    DiscoveredFile(Path(entry.path), stat.st_size, stat.st_mtime_ns)
                                )
                    except OSError:
                        complete, errors = False, errors + 1
        except OSError:
            complete, errors = False, errors + 1
    results.sort(key=lambda item: str(item.path).casefold())
    return ScanResult(results, complete, errors)

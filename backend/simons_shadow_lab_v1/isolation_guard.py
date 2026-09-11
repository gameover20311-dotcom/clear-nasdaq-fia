"""Production-tree isolation guard for Shadow Lab V2.

Adapted from the strongest part of the independent Cloud build: isolation is
measured, not merely asserted. The guard can seal a production tree with SHA256,
verify it after a lab run, and optionally install a process-wide barrier that
blocks common write paths targeting the protected tree.

This is defense in depth. Filesystem permissions remain the real kernel-level
control; subprocess/C-extension writes are outside this Python barrier.
"""
from __future__ import annotations

import builtins
import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator


class ReadOnlyViolation(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_seal(root: Path) -> Dict[str, Any]:
    root = Path(root).resolve()
    files = {}
    if root.exists():
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            rel = str(path.relative_to(root))
            files[rel] = {"sha256": _sha256_file(path), "size": path.stat().st_size}
    body = "\n".join(f"{k}\t{v['size']}\t{v['sha256']}" for k, v in sorted(files.items())).encode("utf-8")
    return {"root": str(root), "file_count": len(files), "files": files, "tree_sha256": hashlib.sha256(body).hexdigest()}


def compare_seal(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    b, a = before.get("files") or {}, after.get("files") or {}
    added = sorted(set(a) - set(b)); removed = sorted(set(b) - set(a))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    return {
        "unchanged": not added and not removed and not changed and before.get("tree_sha256") == after.get("tree_sha256"),
        "added": added,
        "removed": removed,
        "changed": changed,
        "before_tree_sha256": before.get("tree_sha256"),
        "after_tree_sha256": after.get("tree_sha256"),
    }


def _inside(target: Any, protected_root: Path) -> bool:
    try:
        p = Path(os.fspath(target)).expanduser().resolve(strict=False)
    except (TypeError, ValueError, OSError):
        return False
    try:
        p.relative_to(protected_root)
        return True
    except ValueError:
        return False


def _mode_writes(mode: str) -> bool:
    text = str(mode or "r")
    return any(flag in text for flag in ("w", "a", "x", "+"))


def _flags_write(flags: int) -> bool:
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
    return bool(int(flags) & write_flags)


@contextmanager
def production_write_barrier(production_root: Path) -> Iterator[None]:
    root = Path(production_root).resolve()
    original_open = builtins.open
    original_os_open = os.open
    original_remove = os.remove
    original_unlink = os.unlink
    original_rename = os.rename
    original_replace = os.replace
    original_mkdir = os.mkdir

    def guarded_open(file, mode="r", *args, **kwargs):
        if _inside(file, root) and _mode_writes(mode):
            raise ReadOnlyViolation(f"write blocked inside production tree: {file}")
        return original_open(file, mode, *args, **kwargs)

    def guarded_os_open(path, flags, *args, **kwargs):
        if _inside(path, root) and _flags_write(flags):
            raise ReadOnlyViolation(f"os.open write blocked inside production tree: {path}")
        return original_os_open(path, flags, *args, **kwargs)

    def block_one(fn):
        def wrapped(path, *args, **kwargs):
            if _inside(path, root):
                raise ReadOnlyViolation(f"mutation blocked inside production tree: {path}")
            return fn(path, *args, **kwargs)
        return wrapped

    def block_two(fn):
        def wrapped(src, dst, *args, **kwargs):
            if _inside(src, root) or _inside(dst, root):
                raise ReadOnlyViolation(f"rename/replace blocked for production tree: {src} -> {dst}")
            return fn(src, dst, *args, **kwargs)
        return wrapped

    builtins.open = guarded_open
    os.open = guarded_os_open
    os.remove = block_one(original_remove)
    os.unlink = block_one(original_unlink)
    os.rename = block_two(original_rename)
    os.replace = block_two(original_replace)
    os.mkdir = block_one(original_mkdir)
    try:
        yield
    finally:
        builtins.open = original_open
        os.open = original_os_open
        os.remove = original_remove
        os.unlink = original_unlink
        os.rename = original_rename
        os.replace = original_replace
        os.mkdir = original_mkdir


class ProductionGuard:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.before = tree_seal(self.root)

    def verify_unchanged(self) -> Dict[str, Any]:
        after = tree_seal(self.root)
        result = compare_seal(self.before, after)
        result["production_root"] = str(self.root)
        return result

    @contextmanager
    def barrier(self) -> Iterator[None]:
        with production_write_barrier(self.root):
            yield

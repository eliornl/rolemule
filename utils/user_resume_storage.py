"""
On-disk storage for user resume uploads (PDF/DOCX/TXT).

Production deployments can later swap to object storage; callers use paths
relative to ``settings.user_resume_storage_dir``.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)
def _abs_root(base_dir: str) -> Path:
    root = Path(base_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resume_absolute_path(base_dir: str, storage_relative_path: str) -> Path:
    """
    Resolve a DB-stored relative path under the configured root.

    Raises:
        ValueError: If the path escapes the storage root.
    """
    root = _abs_root(base_dir)
    rel = Path(storage_relative_path)
    if rel.is_absolute():
        raise ValueError("Invalid storage path")
    full = (root / rel).resolve()
    try:
        full.relative_to(root)
    except ValueError as e:
        raise ValueError("Path traversal rejected") from e
    return full


def save_resume_bytes(
    base_dir: str, user_id: uuid.UUID, content: bytes, original_filename: str
) -> Tuple[str, str, str]:
    """
    Write resume bytes to ``{root}/{user_id}/{random}.{ext}``.

    Returns:
        Tuple of (storage_relative_path, sha256_hex, normalized_extension_without_dot)
    """
    root = _abs_root(base_dir)
    user_dir = root / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    ext = "bin"
    if original_filename and "." in original_filename:
        raw = original_filename.rsplit(".", 1)[-1].lower()
        if raw in ("pdf", "docx", "txt"):
            ext = raw

    fname = f"{uuid.uuid4().hex}.{ext}"
    rel = f"{user_id}/{fname}"
    dest = user_dir / fname

    h = hashlib.sha256(content).hexdigest()
    dest.write_bytes(content)
    return rel, h, ext


def delete_resume_file(base_dir: str, storage_relative_path: Optional[str]) -> None:
    """Remove the on-disk file if present; ignores missing files."""
    if not storage_relative_path:
        return
    try:
        path = resume_absolute_path(base_dir, storage_relative_path)
    except ValueError as e:
        logger.warning("Refusing to delete resume path %s: %s", storage_relative_path, e)
        return
    try:
        if path.is_file():
            path.unlink()
    except OSError as e:
        logger.warning("Failed to delete resume file %s: %s", path, e, exc_info=True)

    # Remove empty user directory
    try:
        parent = path.parent
        if parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    except OSError as e:
        logger.debug("Could not remove empty resume directory: %s", e, exc_info=True)

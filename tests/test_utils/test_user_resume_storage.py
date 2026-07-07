"""Tests for utils/user_resume_storage.py."""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.user_resume_storage import (
    delete_resume_file,
    resume_absolute_path,
    save_resume_bytes,
)


def test_save_and_resolve_resume(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    content = b"%PDF-1.4 resume bytes"
    rel, sha, ext = save_resume_bytes(str(tmp_path), user_id, content, "resume.pdf")
    assert ext == "pdf"
    assert len(sha) == 64
    assert rel.startswith(str(user_id))

    full = resume_absolute_path(str(tmp_path), rel)
    assert full.is_file()
    assert full.read_bytes() == content


def test_save_unknown_extension_defaults_bin(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    rel, _, ext = save_resume_bytes(str(tmp_path), user_id, b"data", "file.xyz")
    assert ext == "bin"


def test_resume_absolute_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path traversal"):
        resume_absolute_path(str(tmp_path), "../outside.txt")


def test_resume_absolute_path_rejects_absolute(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Invalid storage path"):
        resume_absolute_path(str(tmp_path), "/etc/passwd")


def test_delete_resume_file_removes_file_and_empty_dir(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    rel, _, _ = save_resume_bytes(str(tmp_path), user_id, b"txt content", "cv.txt")
    delete_resume_file(str(tmp_path), rel)
    assert not (tmp_path / rel).exists()
    assert not (tmp_path / str(user_id)).exists()


def test_delete_resume_file_invalid_path_no_raise(tmp_path: Path) -> None:
    delete_resume_file(str(tmp_path), "../../etc/passwd")


def test_delete_resume_file_none_path() -> None:
    delete_resume_file("/tmp", None)


def test_delete_resume_file_oserror_on_unlink(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    rel, _, _ = save_resume_bytes(str(tmp_path), user_id, b"data", "cv.txt")
    full = resume_absolute_path(str(tmp_path), rel)

    with patch.object(Path, "unlink", side_effect=OSError("perm")):
        delete_resume_file(str(tmp_path), rel)
    assert full.is_file()


def test_delete_resume_file_rmdir_oserror(tmp_path: Path) -> None:
    user_id = uuid.uuid4()
    rel, _, _ = save_resume_bytes(str(tmp_path), user_id, b"data", "cv.txt")
    with patch.object(Path, "rmdir", side_effect=OSError("not empty")):
        delete_resume_file(str(tmp_path), rel)
    assert not (tmp_path / rel).exists()

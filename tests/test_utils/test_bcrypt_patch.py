"""Tests for utils/bcrypt_patch.py."""

from unittest.mock import MagicMock, patch

import utils.bcrypt_patch as bp


def test_apply_bcrypt_patch_adds_about(monkeypatch) -> None:
    fake_bcrypt = MagicMock()
    del fake_bcrypt.__about__  # ensure missing
    fake_bcrypt.__version__ = "4.3.0"
    monkeypatch.setitem(__import__("sys").modules, "bcrypt", fake_bcrypt)
    bp.apply_bcrypt_patch()
    assert hasattr(fake_bcrypt, "__about__")
    assert fake_bcrypt.__about__.__version__ == "4.3.0"


def test_apply_bcrypt_patch_skips_when_present(monkeypatch) -> None:
    fake_bcrypt = MagicMock()
    fake_bcrypt.__about__ = MagicMock(__version__="9.9.9")
    monkeypatch.setitem(__import__("sys").modules, "bcrypt", fake_bcrypt)
    bp.apply_bcrypt_patch()
    assert fake_bcrypt.__about__.__version__ == "9.9.9"


def test_apply_bcrypt_patch_import_error(monkeypatch) -> None:
    monkeypatch.delitem(__import__("sys").modules, "bcrypt", raising=False)
    with patch.dict("sys.modules", {"bcrypt": None}):
        with patch("builtins.__import__", side_effect=ImportError("no bcrypt")):
            bp.apply_bcrypt_patch()  # should not raise


def test_apply_bcrypt_patch_generic_error(monkeypatch) -> None:
    fake_bcrypt = MagicMock()
    type(fake_bcrypt).__about__ = property(lambda self: (_ for _ in ()).throw(RuntimeError("fail")))
    monkeypatch.setitem(__import__("sys").modules, "bcrypt", fake_bcrypt)
    bp.apply_bcrypt_patch()  # logs error, no raise

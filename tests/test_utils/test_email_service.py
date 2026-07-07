"""Tests for utils/email_service.py."""

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from utils.email_service import (
    EmailService,
    _sanitize_email_header,
    check_email_health,
    get_email_service,
)


@pytest.fixture(autouse=True)
def reset_email_singleton():
    import utils.email_service as email_mod

    email_mod._email_service = None
    yield
    email_mod._email_service = None


def test_sanitize_email_header_strips_crlf() -> None:
    assert _sanitize_email_header("user@example.com\r\nBcc: evil@x.com") == "user@example.comBcc: evil@x.com"
    assert _sanitize_email_header("safe\x00subject") == "safesubject"


def test_email_service_disabled_when_no_credentials() -> None:
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username=None,
            smtp_password=None,
            smtp_from_email=None,
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert not svc.is_configured()
        assert svc.enabled is False


def test_email_service_enabled_with_credentials() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "app-password"
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert svc.is_configured()
        assert svc.password == "app-password"


@pytest.mark.asyncio
async def test_send_email_not_configured_returns_false() -> None:
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_username=None,
            smtp_password=None,
            smtp_from_email=None,
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert await svc.send_email("a@b.com", "Hi", "<p>Hi</p>") is False


@pytest.mark.asyncio
async def test_send_email_success() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "pw"
    mock_server = MagicMock()
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_server)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("utils.email_service.get_settings") as gs, \
         patch("utils.email_service.smtplib.SMTP", return_value=mock_cm):
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        ok = await svc.send_email(
            "user@example.com",
            "Subject",
            "<p>HTML</p>",
            text_content="Plain",
        )
        assert ok is True
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("sender@example.com", "pw")
        mock_server.sendmail.assert_called_once()


@pytest.mark.asyncio
async def test_send_email_smtp_auth_error() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "pw"
    mock_server = MagicMock()
    mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"bad")
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_server)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("utils.email_service.get_settings") as gs, \
         patch("utils.email_service.smtplib.SMTP", return_value=mock_cm):
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert await svc.send_email("u@x.com", "S", "<p>x</p>") is False


@pytest.mark.asyncio
async def test_send_email_smtp_exception() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "pw"
    mock_server = MagicMock()
    mock_server.sendmail.side_effect = smtplib.SMTPException("fail")
    mock_cm = MagicMock()
    mock_cm.__enter__ = MagicMock(return_value=mock_server)
    mock_cm.__exit__ = MagicMock(return_value=False)

    with patch("utils.email_service.get_settings") as gs, \
         patch("utils.email_service.smtplib.SMTP", return_value=mock_cm):
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert await svc.send_email("u@x.com", "S", "<p>x</p>") is False


@pytest.mark.asyncio
async def test_send_email_generic_exception() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "pw"
    with patch("utils.email_service.get_settings") as gs, \
         patch("utils.email_service.smtplib.SMTP", side_effect=RuntimeError("boom")):
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        svc = EmailService()
        assert await svc.send_email("u@x.com", "S", "<p>x</p>") is False


@pytest.mark.asyncio
async def test_template_methods_delegate_to_send_email() -> None:
    secret = MagicMock()
    secret.get_secret_value.return_value = "pw"
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password=secret,
            smtp_from_email="sender@example.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000/",
        )
        svc = EmailService()
        with patch.object(svc, "send_email", return_value=True) as send:
            assert await svc.send_password_reset_email(
                "u@x.com", "tok", "https://app/reset?token=tok", user_name="Jane<script>"
            )
            assert await svc.send_welcome_email("u@x.com", user_name="Bob")
            assert await svc.send_verification_email(
                "u@x.com", "tok", "https://app/verify?token=tok"
            )
            assert await svc.send_verification_code_email("u@x.com", "123456")
            assert send.call_count == 4


def test_get_email_service_singleton() -> None:
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_username=None,
            smtp_password=None,
            smtp_from_email=None,
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        a = get_email_service()
        b = get_email_service()
        assert a is b


@pytest.mark.asyncio
async def test_check_email_health() -> None:
    with patch("utils.email_service.get_settings") as gs:
        gs.return_value = MagicMock(
            smtp_username="a@b.com",
            smtp_password=MagicMock(get_secret_value=lambda: "pw"),
            smtp_from_email="a@b.com",
            smtp_from_name="ApplyPilot",
            base_url="http://localhost:8000",
        )
        assert await check_email_health() is True

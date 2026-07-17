"""Tests for rolemule tools commands."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from rolemule_client.errors import ApiClientError, ExitCode

THANK_YOU_RESPONSE = {
    "subject_line": "Thank you for the interview",
    "email_body": "Dear Jane, thank you for your time today.",
    "tone": "professional",
}

FOLLOWUP_STAGES = {
    "stages": [{"value": "after_interview", "label": "After interview"}],
}

REJECTION_RESPONSE = {
    "analysis_summary": "Skills mismatch",
    "likely_reasons": ["Missing Kubernetes"],
    "improvement_suggestions": ["Add cloud projects"],
}


def test_tools_followup_stages(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.followup_stages.return_value = FOLLOWUP_STAGES

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke("tools", "followup-stages")
    assert result.exit_code == 0
    assert "after_interview" in result.output


def test_tools_thank_you_human(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.thank_you.return_value = THANK_YOU_RESPONSE

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "thank-you",
            "--interviewer",
            "Jane Smith",
            "--interview-type",
            "video",
            "--company",
            "Acme",
            "--title",
            "Engineer",
        )
    assert result.exit_code == 0
    assert "Thank you for the interview" in result.output
    assert "Dear Jane" in result.output


def test_tools_thank_you_json(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.thank_you.return_value = THANK_YOU_RESPONSE

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "--format",
            "json",
            "tools",
            "thank-you",
            "--interviewer",
            "Jane",
            "--interview-type",
            "video",
            "--company",
            "Acme",
            "--title",
            "Engineer",
        )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["subject_line"] == THANK_YOU_RESPONSE["subject_line"]


def test_tools_thank_you_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "req.json"
    req.write_text(
        json.dumps(
            {
                "interviewer_name": "Jane",
                "interview_type": "phone",
                "company_name": "Acme",
                "job_title": "Engineer",
            }
        ),
        encoding="utf-8",
    )
    mock_client = MagicMock()
    mock_client.tools.thank_you.return_value = THANK_YOU_RESPONSE

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke("tools", "thank-you", "--file", str(req))
    assert result.exit_code == 0
    mock_client.tools.thank_you.assert_called_once()


def test_tools_followup_post(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.followup.return_value = {
        "subject_line": "Following up",
        "email_body": "Hi team, checking in…",
    }

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "followup",
            "--stage",
            "after_interview",
            "--company",
            "Acme",
            "--title",
            "Engineer",
        )
    assert result.exit_code == 0
    assert "Following up" in result.output


def test_tools_salary_coach(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.salary_coach.return_value = {
        "job_title": "Engineer",
        "company_name": "Acme",
        "offered_salary": "$155,000",
        "strategy_overview": {"recommended_approach": "Collaborative"},
        "walk_away_point": "$160k",
    }

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "salary-coach",
            "--title",
            "Engineer",
            "--company",
            "Acme",
            "--offered",
            "$155,000",
        )
    assert result.exit_code == 0
    assert "Salary coach" in result.output
    assert "Collaborative" in result.output


def test_tools_rejection_analysis(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.rejection_analysis.return_value = REJECTION_RESPONSE

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "rejection-analysis",
            "--email",
            "Thank you for applying. We chose another candidate.",
        )
    assert result.exit_code == 0
    assert "Rejection analysis" in result.output
    assert "Kubernetes" in result.output


def test_tools_reference_request(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.reference_request.return_value = {
        "subject_line": "Reference request",
        "email_body": "Dear Alex, could you serve as a reference?",
        "tips": ["Send a brief note"],
    }

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "reference-request",
            "--name",
            "Alex Rivera",
            "--relationship",
            "Former manager",
        )
    assert result.exit_code == 0
    assert "Reference request" in result.output
    assert "brief note" in result.output


def test_tools_job_comparison_requires_file(invoke, write_credentials) -> None:
    write_credentials()
    result = invoke("tools", "job-comparison")
    assert result.exit_code != 0


def test_tools_job_comparison_from_file(invoke, write_credentials, tmp_path: Path) -> None:
    write_credentials()
    req = tmp_path / "jobs.json"
    req.write_text(
        json.dumps({"jobs": [{"title": "A", "company": "X"}, {"title": "B", "company": "Y"}]}),
        encoding="utf-8",
    )
    mock_client = MagicMock()
    mock_client.tools.job_comparison.return_value = {
        "recommended_job": "A @ X",
        "executive_summary": "Better fit",
        "jobs_analysis": [{"title": "A", "company": "X", "overall_score": 85}],
    }

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke("tools", "job-comparison", "--file", str(req))
    assert result.exit_code == 0
    assert "Job comparison" in result.output
    assert "Better fit" in result.output


def test_tools_schema_thank_you(invoke) -> None:
    result = invoke("tools", "schema", "thank-you")
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["interviewer_name"]
    assert payload["company_name"]


def test_tools_rate_limit(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.salary_coach.side_effect = ApiClientError(
        message="Rate limit exceeded",
        status_code=429,
        error_code="RATE_4001",
        exit_code=ExitCode.RATE_LIMITED,
    )

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "salary-coach",
            "--title",
            "Eng",
            "--company",
            "Acme",
            "--offered",
            "$100k",
        )
    assert result.exit_code == int(ExitCode.RATE_LIMITED)


def test_tools_cfg_6001_hint(invoke, write_credentials) -> None:
    write_credentials()
    mock_client = MagicMock()
    mock_client.tools.thank_you.side_effect = ApiClientError(
        message="No API key configured",
        status_code=422,
        error_code="CFG_6001",
        exit_code=ExitCode.ERROR,
    )

    with patch("cli.commands.tools.require_client", return_value=mock_client):
        result = invoke(
            "tools",
            "thank-you",
            "--interviewer",
            "Jane",
            "--interview-type",
            "video",
            "--company",
            "Acme",
            "--title",
            "Eng",
        )
    assert result.exit_code != 0
    assert "API key" in result.output or "Settings" in result.output

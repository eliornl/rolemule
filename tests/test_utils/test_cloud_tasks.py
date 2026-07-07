"""Tests for utils/cloud_tasks.py."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.cloud_tasks as ct


def test_verify_cloud_tasks_secret() -> None:
    with patch("utils.cloud_tasks.get_settings") as gs:
        gs.return_value = MagicMock(cloud_tasks_secret="super-secret")
        assert ct.verify_cloud_tasks_secret("super-secret") is True
        assert ct.verify_cloud_tasks_secret("wrong") is False
        assert ct.verify_cloud_tasks_secret(None) is False


def test_extract_project_from_env() -> None:
    with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "my-project"}):
        assert ct._extract_project_from_service_url("https://svc.run.app") == "my-project"


def test_extract_project_missing_raises() -> None:
    with patch.dict(os.environ, {}, clear=True):
        os.environ.pop("GOOGLE_CLOUD_PROJECT", None)
        os.environ.pop("GCLOUD_PROJECT", None)
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
            ct._extract_project_from_service_url("https://svc.run.app")


@pytest.mark.asyncio
async def test_enqueue_workflow_task_calls_internal() -> None:
    with patch.object(ct, "_enqueue_task", AsyncMock()) as enq:
        await ct.enqueue_workflow_task(
            session_id="s1",
            user_id="u1",
            input_method="text",
            job_input="job text",
            user_data={"name": "Test"},
        )
        enq.assert_awaited_once()


@pytest.mark.asyncio
async def test_enqueue_continue_workflow_task() -> None:
    with patch.object(ct, "_enqueue_task", AsyncMock()) as enq:
        await ct.enqueue_continue_workflow_task(session_id="s1", user_id="u1")
        enq.assert_awaited_once()
        assert enq.call_args.kwargs["payload"]["action"] == "continue"


@pytest.mark.asyncio
async def test_enqueue_task_not_available_raises() -> None:
    with patch.object(ct, "_TASKS_AVAILABLE", False):
        with pytest.raises(RuntimeError, match="google-cloud-tasks"):
            await ct._enqueue_task(settings=MagicMock(), payload={})


def test_get_tasks_client() -> None:
    mock_client = MagicMock()
    with patch.object(ct, "tasks_v2", MagicMock(CloudTasksClient=MagicMock(return_value=mock_client))):
        assert ct._get_tasks_client() is mock_client


@pytest.mark.asyncio
async def test_enqueue_task_success() -> None:
    mock_client = MagicMock()
    mock_client.queue_path.return_value = "projects/p/locations/l/queues/q"
    mock_client.create_task = MagicMock()

    settings = MagicMock(
        cloud_tasks_service_url="https://svc.run.app",
        cloud_tasks_location="us-central1",
        cloud_tasks_queue_name="workflow",
        cloud_tasks_secret="sec",
        cloud_tasks_service_account="sa@p.iam.gserviceaccount.com",
    )

    with patch.object(ct, "_TASKS_AVAILABLE", True), \
         patch.object(ct, "_extract_project_from_service_url", return_value="proj"), \
         patch.object(ct, "_get_tasks_client", return_value=mock_client), \
         patch.object(ct, "tasks_v2", MagicMock(
             Task=MagicMock,
             HttpRequest=MagicMock,
             HttpMethod=MagicMock(POST="POST"),
             OidcToken=MagicMock,
         )), \
         patch.object(ct, "duration_pb2", MagicMock(Duration=MagicMock)):
        await ct._enqueue_task(settings=settings, payload={"session_id": "x"})
        mock_client.create_task.assert_called_once()


def test_import_error_marks_tasks_unavailable(monkeypatch) -> None:
    import builtins
    import importlib
    import sys

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google.cloud" or name.startswith("google.cloud."):
            raise ImportError("blocked for test")
        if name == "google.protobuf" or name.startswith("google.protobuf."):
            raise ImportError("blocked for test")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    sys.modules.pop("utils.cloud_tasks", None)
    reloaded = importlib.import_module("utils.cloud_tasks")
    assert reloaded._TASKS_AVAILABLE is False
    assert reloaded.tasks_v2 is None
    sys.modules.pop("utils.cloud_tasks", None)
    importlib.import_module("utils.cloud_tasks")

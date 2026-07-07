"""
Conftest for workflow unit tests.

Stubs GCP packages (Cloud Tasks, Pub/Sub) before workflow modules import them.
"""

import sys
from unittest.mock import MagicMock

_GCP_STUBS = [
    "google.cloud.tasks_v2",
    "google.cloud.tasks_v2.services",
    "google.cloud.tasks_v2.services.cloud_tasks",
    "google.cloud.tasks_v2.types",
    "google.cloud.pubsub_v1",
]
for _mod in _GCP_STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

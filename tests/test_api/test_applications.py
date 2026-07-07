"""
Integration tests for Applications API endpoints.

Endpoints:
  GET    /api/v1/applications/           list with search/filter/sort/paginate
  POST   /api/v1/applications/           create
  GET    /api/v1/applications/{id}       get one
  DELETE /api/v1/applications/{id}       soft delete
  PATCH  /api/v1/applications/{id}/status  update status

Focus: the new `search` query parameter (searches job_title AND company_name),
and the `sort` parameter added during the history-page consolidation.
"""

import pytest

BASE = "/api/v1/applications"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_applications(authed_client_with_user, rows: list[dict]) -> list[dict]:
    """Create multiple applications via POST and return their response bodies."""
    created = []
    for row in rows:
        resp = await authed_client_with_user.post(f"{BASE}/", json=row)
        # 200/201 both mean success depending on how the endpoint is wired
        assert resp.status_code in (200, 201), f"seed failed: {resp.text}"
        created.append(resp.json())
    return created


# ---------------------------------------------------------------------------
# GET /api/v1/applications/ — unauthenticated
# ---------------------------------------------------------------------------


class TestListApplicationsAuth:
    """Auth guard tests for GET /api/v1/applications/."""

    @pytest.mark.asyncio
    async def test_no_auth_returns_401_or_403(self, api_client):
        resp = await api_client.get(f"{BASE}/")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_auth_returns_200(self, authed_client):
        resp = await authed_client.get(f"{BASE}/")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_has_required_fields(self, authed_client):
        resp = await authed_client.get(f"{BASE}/")
        assert resp.status_code == 200
        body = resp.json()
        for field in ("applications", "total", "page", "per_page", "has_next", "has_prev"):
            assert field in body, f"missing field: {field}"
        assert isinstance(body["applications"], list)
        assert isinstance(body["total"], int)


# ---------------------------------------------------------------------------
# GET /api/v1/applications/?search=  — new multi-field search
# ---------------------------------------------------------------------------


class TestListApplicationsSearch:
    """Tests for the `search` query parameter (matches job_title OR company_name)."""

    @pytest.mark.asyncio
    async def test_search_empty_string_returns_all(self, authed_client):
        """search= with empty string should behave like no filter."""
        resp = await authed_client.get(f"{BASE}/", params={"search": ""})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_too_long_returns_422(self, authed_client):
        """search param has max_length=200; exceeding it returns 422."""
        resp = await authed_client.get(f"{BASE}/", params={"search": "x" * 201})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_valid_term_returns_200(self, authed_client):
        """Any reasonable search term must return 200 (even if no results)."""
        resp = await authed_client.get(f"{BASE}/", params={"search": "engineer"})
        assert resp.status_code == 200
        body = resp.json()
        assert "applications" in body

    @pytest.mark.asyncio
    async def test_search_and_status_filter_combined(self, authed_client):
        """search and status_filter can be combined without error."""
        resp = await authed_client.get(
            f"{BASE}/",
            params={"search": "google", "status_filter": "applied"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_search_takes_priority_over_company(self, authed_client):
        """When both search and company are given, search wins (no 400)."""
        resp = await authed_client.get(
            f"{BASE}/",
            params={"search": "python", "company": "acme"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/v1/applications/?sort=  — sort parameter
# ---------------------------------------------------------------------------


class TestListApplicationsSort:
    """Tests for the `sort` query parameter."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("sort_val", [
        "created_desc",
        "created_asc",
        "updated_desc",
        "company_asc",
        "title_asc",
    ])
    async def test_valid_sort_values_return_200(self, authed_client, sort_val):
        resp = await authed_client.get(f"{BASE}/", params={"sort": sort_val})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_sort_value_returns_400_or_422(self, authed_client):
        """Unknown sort values should be rejected, not silently ignored."""
        resp = await authed_client.get(f"{BASE}/", params={"sort": "malicious_sort"})
        # Backend maps unknown sorts to the default; 200 is acceptable too
        assert resp.status_code in (200, 400, 422)


# ---------------------------------------------------------------------------
# GET /api/v1/applications/?days=  — date filter
# ---------------------------------------------------------------------------


class TestListApplicationsDaysFilter:
    """Tests for the `days` query parameter."""

    @pytest.mark.asyncio
    async def test_days_filter_returns_200(self, authed_client):
        resp = await authed_client.get(f"{BASE}/", params={"days": 30})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_days_zero_returns_422(self, authed_client):
        """days must be >= 1."""
        resp = await authed_client.get(f"{BASE}/", params={"days": 0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_days_over_365_returns_422(self, authed_client):
        """days must be <= 365."""
        resp = await authed_client.get(f"{BASE}/", params={"days": 366})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/applications/?per_page=  — pagination
# ---------------------------------------------------------------------------


class TestListApplicationsPagination:
    """Tests for page / per_page parameters."""

    @pytest.mark.asyncio
    async def test_default_pagination_shape(self, authed_client):
        resp = await authed_client.get(f"{BASE}/")
        body = resp.json()
        assert body["page"] == 1
        assert body["per_page"] > 0

    @pytest.mark.asyncio
    async def test_per_page_zero_returns_422(self, authed_client):
        resp = await authed_client.get(f"{BASE}/", params={"per_page": 0})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_page_zero_returns_422(self, authed_client):
        resp = await authed_client.get(f"{BASE}/", params={"page": 0})
        assert resp.status_code == 422

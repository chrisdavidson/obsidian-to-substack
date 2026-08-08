"""Datawrapper API client for publishing tables."""

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

BASE_URL = "https://api.datawrapper.de/v3"


def _request(
    method: str,
    path: str,
    api_token: str,
    data: bytes | None = None,
    content_type: str = "application/json",
) -> dict | None:
    """Make an authenticated request to the Datawrapper API."""
    url = f"{BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": content_type,
    }

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            if body:
                return json.loads(body)
            return None
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        logger.error(
            "Datawrapper API %s %s failed (%d): %s",
            method, path, exc.code, error_body,
        )
        raise RuntimeError(
            f"Datawrapper API error {exc.code}: {error_body}"
        ) from exc


def create_chart(title: str, api_token: str) -> str:
    """Create a new table chart. Returns the chart ID."""
    payload = json.dumps({"title": title, "type": "tables"}).encode("utf-8")
    result = _request("POST", "/charts", api_token, data=payload)
    chart_id = result["id"]
    logger.info("Created Datawrapper chart: %s (id: %s)", title, chart_id)
    return chart_id


def upload_data(chart_id: str, csv_data: str, api_token: str) -> None:
    """Upload CSV data to a chart."""
    _request(
        "PUT",
        f"/charts/{chart_id}/data",
        api_token,
        data=csv_data.encode("utf-8"),
        content_type="text/csv",
    )
    logger.info("Uploaded data to chart %s", chart_id)


def publish_chart(chart_id: str, api_token: str) -> str:
    """Publish a chart and return the public URL."""
    result = _request("POST", f"/charts/{chart_id}/publish", api_token)
    data = result["data"]
    if isinstance(data, list):
        public_url = data[0]["publicUrl"]
    else:
        public_url = data["publicUrl"]
    logger.info("Published chart %s: %s", chart_id, public_url)
    return public_url


def export_chart_png(chart_id: str, api_token: str) -> bytes:
    """Export a published chart as PNG. Returns the raw image bytes."""
    url = f"{BASE_URL}/charts/{chart_id}/export/png"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "image/png",
    }
    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8") if exc.fp else ""
        logger.error(
            "Datawrapper PNG export for %s failed (%d): %s",
            chart_id, exc.code, error_body,
        )
        raise RuntimeError(
            f"Datawrapper PNG export error {exc.code}: {error_body}"
        ) from exc


def publish_table(csv_data: str, title: str, api_token: str) -> tuple[str, str]:
    """Create, upload, publish a table in one call.

    Returns (public_embed_url, chart_id).
    """
    chart_id = create_chart(title, api_token)
    upload_data(chart_id, csv_data, api_token)
    public_url = publish_chart(chart_id, api_token)
    return public_url, chart_id

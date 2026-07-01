import requests


def fetch_screenshot(base_url: str, api_key: str, timeout: float = 15.0) -> dict:
    """Call the Windows agent's /screenshot endpoint.

    Expected response shape (windows-agent contract): a single image of
    whichever monitor currently holds the focused window.
        {
          "captured_at": "2026-07-01T13:20:00+00:00",  # ISO 8601, UTC
          "monitor_index": 1,
          "window_title": "Instagram - Google Chrome",  # nullable
          "png_base64": "..."
        }
    """
    response = requests.get(
        f"{base_url.rstrip('/')}/screenshot",
        headers={"X-API-Key": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()

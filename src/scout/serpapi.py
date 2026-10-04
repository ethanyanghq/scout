"""The one request every SerpApi search makes, whether for flights or hotels."""

import json
import urllib.error
import urllib.parse
import urllib.request

SERPAPI_URL = "https://serpapi.com/search.json"
# A Google search often takes several seconds on SerpApi's side.
TIMEOUT_SECONDS = 30


class SerpApiError(Exception):
    """SerpApi couldn't be reached or refused a search."""


def search_serpapi(api_url: str, api_key: str, engine: str, params: dict) -> dict:
    query = urllib.parse.urlencode({"engine": engine, **params, "api_key": api_key})
    try:
        with urllib.request.urlopen(
            f"{api_url}?{query}", timeout=TIMEOUT_SECONDS
        ) as reply:
            return json.load(reply)
    except urllib.error.HTTPError as error:
        raise SerpApiError(
            f"search failed with {error.code}: {_error_reason(error)}"
        ) from None
    except (urllib.error.URLError, TimeoutError) as error:
        raise SerpApiError(f"search didn't connect: {error}") from None
    except json.JSONDecodeError as error:
        raise SerpApiError(f"search sent an unexpected reply: {error}") from None


def _error_reason(error: urllib.error.HTTPError) -> str:
    """SerpApi's own explanation, e.g. "Invalid API key.", if it sent one."""
    body = error.read().decode(errors="replace")
    try:
        return json.loads(body)["error"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return body[:200]

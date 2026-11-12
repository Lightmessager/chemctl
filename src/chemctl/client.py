import os

import httpx


class APIError(Exception):
    def __init__(self, response):
        self.response = response
        super().__init__(response["error"]["message"])


class Client:
    def __init__(self, url=None):
        self.url = (url or os.environ.get("CHEMCTL_URL", "http://127.0.0.1:8765")).rstrip("/")

    def call(self, method, path, **kwargs):
        try:
            response = httpx.request(method, self.url + path, timeout=httpx.Timeout(120, connect=10), **kwargs)
        except httpx.HTTPError as exc:
            raise APIError({"ok": False, "data": None, "error": {"code": "API_UNAVAILABLE", "message": f"{exc}. Start the service with chemctl serve."}, "meta": {}}) from exc
        try:
            result = response.json()
        except ValueError:
            result = {"ok": False, "data": None, "error": {"code": "INVALID_API_RESPONSE", "message": f"HTTP {response.status_code}: API returned a non-JSON response."}, "meta": {}}
        if not response.is_success or result.get("ok") is False:
            if not result.get("error"):
                result = {"ok": False, "data": None, "error": {"code": "HTTP_ERROR", "message": f"HTTP {response.status_code}"}, "meta": {}}
            raise APIError(result)
        return result

    def get(self, path, **params):
        return self.call("GET", "/api/v1" + path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path, **data):
        return self.call("POST", "/api/v1" + path, json=data)

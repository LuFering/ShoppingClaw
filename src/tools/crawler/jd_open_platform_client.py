from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def _md5_hex(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class JdOpenPlatformRequest:
    url: str
    method: str
    params: dict[str, Any]
    json: dict[str, Any] | None
    headers: dict[str, str]
    timeout_s: float


class JdOpenPlatformClient:
    def __init__(
        self,
        *,
        base_url: str,
        endpoint: str,
        http_method: str = "GET",
        timeout_s: float = 10.0,
        app_key: str | None = None,
        app_secret: str | None = None,
        access_token: str | None = None,
        sign_mode: str = "none",
        sign_param_name: str = "sign",
        app_key_param_name: str = "app_key",
        dry_run: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.endpoint = endpoint.lstrip("/")
        self.http_method = http_method.strip().upper() or "GET"
        self.timeout_s = timeout_s
        self.app_key = (app_key or "").strip() or None
        self.app_secret = (app_secret or "").strip() or None
        self.access_token = (access_token or "").strip() or None
        self.sign_mode = (sign_mode or "none").strip().lower()
        self.sign_param_name = (sign_param_name or "sign").strip()
        self.app_key_param_name = (app_key_param_name or "app_key").strip()
        self.dry_run = dry_run

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str | None,
        endpoint: str | None,
        app_key: str | None,
        app_secret: str | None,
        access_token: str | None,
    ) -> "JdOpenPlatformClient":
        import os

        timeout_s = float((os.getenv("JD_OPEN_PLATFORM_TIMEOUT_SECONDS") or "10").strip() or "10")
        http_method = (os.getenv("JD_OPEN_PLATFORM_HTTP_METHOD") or "GET").strip()
        sign_mode = (os.getenv("JD_OPEN_PLATFORM_SIGN_MODE") or "none").strip()
        sign_param_name = (os.getenv("JD_OPEN_PLATFORM_SIGN_PARAM_NAME") or "sign").strip()
        app_key_param_name = (os.getenv("JD_OPEN_PLATFORM_APP_KEY_PARAM_NAME") or "app_key").strip()
        dry_run = _truthy(os.getenv("JD_OPEN_PLATFORM_DRY_RUN"))

        if not base_url:
            raise RuntimeError("JD open platform base_url not configured")
        if not endpoint:
            raise RuntimeError("JD open platform search endpoint not configured")

        return cls(
            base_url=base_url,
            endpoint=endpoint,
            http_method=http_method,
            timeout_s=timeout_s,
            app_key=app_key,
            app_secret=app_secret,
            access_token=access_token,
            sign_mode=sign_mode,
            sign_param_name=sign_param_name,
            app_key_param_name=app_key_param_name,
            dry_run=dry_run,
        )

    def build_payload(self, *, query: str, limit: int) -> dict[str, Any]:
        payload: dict[str, Any] = {"query": query, "limit": int(limit)}
        if self.app_key:
            payload[self.app_key_param_name] = self.app_key
        return payload

    def sign(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.sign_mode == "none":
            return params
        if self.sign_mode != "md5_sorted_secret":
            raise RuntimeError(f"Unsupported JD sign_mode: {self.sign_mode}")
        if not self.app_secret:
            raise RuntimeError("JD open platform app_secret not configured for signing")

        material = "".join(f"{k}{params[k]}" for k in sorted(params.keys())) + self.app_secret
        return {**params, self.sign_param_name: _md5_hex(material)}

    def build_request(self, *, query: str, limit: int) -> JdOpenPlatformRequest:
        payload = self.build_payload(query=query, limit=limit)
        payload = self.sign(payload)

        headers: dict[str, str] = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        url = f"{self.base_url}/{self.endpoint}"
        if self.http_method == "POST":
            return JdOpenPlatformRequest(
                url=url,
                method="POST",
                params={},
                json=payload,
                headers=headers,
                timeout_s=self.timeout_s,
            )
        return JdOpenPlatformRequest(
            url=url,
            method="GET",
            params=payload,
            json=None,
            headers=headers,
            timeout_s=self.timeout_s,
        )

    def call(self, *, query: str, limit: int) -> Any:
        if self.dry_run:
            return {}

        req = self.build_request(query=query, limit=limit)

        try:
            with httpx.Client(timeout=req.timeout_s) as client:
                if req.method == "POST":
                    resp = client.post(req.url, json=req.json, headers=req.headers)
                else:
                    resp = client.get(req.url, params=req.params, headers=req.headers)
                resp.raise_for_status()
                return resp.json()
        except httpx.RequestError as exc:
            raise RuntimeError(f"JD open platform request failed: {exc.__class__.__name__}") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"JD open platform http error: {exc.response.status_code}") from exc
        except Exception as exc:
            raise RuntimeError(f"JD open platform response parse failed: {exc.__class__.__name__}") from exc


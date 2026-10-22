"""Native file uploads via ImgBB, or an owner-operated upload endpoint."""

import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from dotenv import dotenv_values

from . import config
from .images import FORMATS, ImageError, inspect_image, normalize_image_url


class UploadError(ImageError):
    pass


def local_owner_settings():
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
        roots = [root, root.parent] if root.name.lower() == "dist" else [root]
    else:
        roots = [Path(__file__).resolve().parents[1]]
    values = {}
    for root in roots:
        path = root / ".env"
        if path.is_file():
            settings = dotenv_values(path, interpolate=False, encoding="utf-8-sig")
            settings = {name.upper(): value for name, value in settings.items()}
            for name in ("IMGBB_API_KEY", "CUSTOMPRESENCE_UPLOAD_URL"):
                value = settings.get(name)
                if isinstance(value, str) and value.strip():
                    values.setdefault(name, value.strip())
    return values


def owner_upload_key(settings=None):
    settings = local_owner_settings() if settings is None else settings
    value = (os.getenv("IMGBB_API_KEY", "") or settings.get("IMGBB_API_KEY", "")).strip()
    if value or sys.platform != "win32":
        return value
    # Double-clicked Windows apps can inherit an older Explorer environment.
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "IMGBB_API_KEY")
            return value.strip() if isinstance(value, str) else ""
    except OSError:
        return ""


def hosted_url(value, hosts):
    try:
        value = normalize_image_url(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise UploadError(502, "The upload host returned an invalid image link. Try again.") from exc
    if urlsplit(value).hostname not in hosts:
        raise UploadError(502, "The upload host returned an unexpected image address.")
    return value


class ImgBBUploads:
    def __init__(self, api_key=None, relay_url=None, client=None):
        settings = local_owner_settings() if api_key is None or relay_url is None else {}
        self.api_key = owner_upload_key(settings) if api_key is None else api_key.strip()
        self.relay_url = ((os.getenv("CUSTOMPRESENCE_UPLOAD_URL") or settings.get("CUSTOMPRESENCE_UPLOAD_URL") or config.UPLOAD_SERVICE_URL)
                          if relay_url is None else relay_url).strip()
        if self.relay_url:
            self.relay_url = normalize_image_url(self.relay_url)
        self.client = client

    @property
    def enabled(self):
        return bool(self.relay_url or self.api_key)

    def configuration(self):
        return {"enabled": self.enabled, "provider": "ImgBB", "flow": "native",
                "via_service": bool(self.relay_url)}

    async def upload(self, data):
        if not self.enabled:
            raise UploadError(503, "Uploads aren't configured in this build yet. You can paste a public image link.")
        info = await asyncio.to_thread(inspect_image, data)
        owns_client = self.client is None
        client = self.client or httpx.AsyncClient(timeout=60, follow_redirects=False, trust_env=False)
        try:
            if self.relay_url:
                response = await client.post(self.relay_url, content=data,
                                             headers={"Content-Type": "application/octet-stream"})
            else:
                extension, mime = FORMATS[info["format"]]
                # Keep the account key out of request URLs and the original filename private.
                response = await client.post("https://api.imgbb.com/1/upload", data={"key": self.api_key},
                                             files={"image": (f"image.{extension}", data, mime)})
            if response.status_code == 429:
                raise UploadError(429, "The upload service is busy or its limit was reached. Wait and try again.")
            if response.status_code in {400, 401, 403}:
                raise UploadError(503, "The upload host refused this upload. Its account configuration or content rules may prevent it.")
            if response.status_code >= 300:
                raise UploadError(502, "The upload host is unavailable. Try again later or paste a public image link.")
            try:
                payload = response.json()
                if self.relay_url:
                    result = payload
                else:
                    if payload.get("success") is not True:
                        raise ValueError
                    result = payload["data"]
                url = hosted_url(result["url"], {"i.ibb.co"})
                deletion = result.get("delete_url", "")
                if deletion:
                    deletion = hosted_url(deletion, {"ibb.co"})
                return {"url": url, "delete_url": deletion, **info}
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                raise UploadError(502, "The upload host returned an invalid response. Try again later.") from exc
        except httpx.HTTPError as exc:
            raise UploadError(502, "The upload could not reach ImgBB. Check your connection and try again.") from exc
        finally:
            if owns_client:
                await client.aclose()

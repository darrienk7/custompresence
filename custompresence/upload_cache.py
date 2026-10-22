"""Remember each uploaded file by its contents instead of uploading it again."""

import asyncio
import hashlib
import json
import logging
import time
from pathlib import Path

import httpx

from .imgbb import hosted_url
from .images import ImageError


logger = logging.getLogger(__name__)


async def cached_image_available(url):
    """Only a definite removal should cause another upload during a host outage."""
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False, trust_env=False) as client:
            response = await client.head(url)
        return response.status_code not in {404, 410}
    except httpx.HTTPError:
        return True


class UploadCache:
    def __init__(self, path: Path, uploader, *, check=cached_image_available, limit=100):
        self.path = path
        self.uploader = uploader
        self.check = check
        self.limit = limit
        self.lock = asyncio.Lock()
        self.entries = self._load()

    def _load(self):
        try:
            if self.path.stat().st_size > 1_000_000:
                return {}
            entries = json.loads(self.path.read_text(encoding="utf-8")).get("images", {})
            result = {}
            for digest, entry in entries.items():
                if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                    continue
                image = entry["image"]
                image["url"] = hosted_url(image["url"], {"i.ibb.co"})
                if image.get("delete_url"):
                    image["delete_url"] = hosted_url(image["delete_url"], {"ibb.co"})
                if not isinstance(entry["last_used"], (int, float)):
                    continue
                result[digest] = entry
            return dict(sorted(result.items(), key=lambda item: item[1]["last_used"])[-self.limit:])
        except (OSError, ValueError, KeyError, TypeError, AttributeError, ImageError):
            return {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        try:
            temporary.write_text(json.dumps({"images": self.entries}, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    async def upload(self, data):
        digest = hashlib.sha256(data).hexdigest()
        async with self.lock:
            entry = self.entries.get(digest)
            reused = False
            if entry is not None and await self.check(entry["image"]["url"]):
                image = entry["image"]
                reused = True
            else:
                image = await self.uploader.upload(data)
            self.entries[digest] = {"image": image, "last_used": time.time()}
            self.entries = dict(sorted(self.entries.items(), key=lambda item: item[1]["last_used"])[-self.limit:])
            remembered = True
            try:
                await asyncio.to_thread(self._save)
            except OSError:
                remembered = False
                logger.warning("Could not save upload reuse history")
            return {**image, "reused": reused, "remembered": remembered}

    async def clear(self):
        async with self.lock:
            await asyncio.to_thread(self.path.unlink, missing_ok=True)
            await asyncio.to_thread(self.path.with_suffix(".tmp").unlink, missing_ok=True)
            self.entries.clear()

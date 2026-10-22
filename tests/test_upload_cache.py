import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

from custompresence.upload_cache import UploadCache, cached_image_available


IMAGE = {"url": "https://i.ibb.co/test/example.gif", "delete_url": "https://ibb.co/test/remove",
         "format": "GIF", "width": 64, "height": 64}


class UploadCacheTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "uploads.json"
        self.uploader = Mock(upload=AsyncMock(return_value=IMAGE.copy()))
        self.check = AsyncMock(return_value=True)
        self.cache = UploadCache(self.path, self.uploader, check=self.check)

    async def test_identical_contents_reuse_upload_even_after_restart(self):
        first = await self.cache.upload(b"file contents")
        self.assertFalse(first["reused"])
        self.assertTrue(first["remembered"])
        restarted = UploadCache(self.path, self.uploader, check=self.check)
        second = await restarted.upload(b"file contents")
        self.assertTrue(second["reused"])
        self.assertEqual(second["delete_url"], IMAGE["delete_url"])
        self.uploader.upload.assert_awaited_once_with(b"file contents")
        self.check.assert_awaited_once_with(IMAGE["url"])
        saved = self.path.read_text(encoding="utf-8")
        self.assertNotIn("file contents", saved)
        self.assertIn(hashlib.sha256(b"file contents").hexdigest(), saved)

    async def test_distinct_files_upload_separately_and_history_is_bounded(self):
        self.cache.limit = 2
        for contents in (b"first", b"second", b"third"):
            await self.cache.upload(contents)
        self.assertEqual(self.uploader.upload.await_count, 3)
        self.assertEqual(len(self.cache.entries), 2)
        self.assertNotIn(hashlib.sha256(b"first").hexdigest(), self.cache.entries)
        self.assertEqual(len(json.loads(self.path.read_text())["images"]), 2)

    async def test_removed_hosted_file_is_uploaded_again(self):
        await self.cache.upload(b"file")
        self.check.return_value = False
        replacement = IMAGE | {"url": "https://i.ibb.co/test/replacement.gif"}
        self.uploader.upload.return_value = replacement
        result = await self.cache.upload(b"file")
        self.assertFalse(result["reused"])
        self.assertEqual(result["url"], replacement["url"])
        self.assertEqual(self.uploader.upload.await_count, 2)

    async def test_concurrent_identical_files_create_one_remote_upload(self):
        results = await asyncio.gather(self.cache.upload(b"same"), self.cache.upload(b"same"))
        self.assertEqual([result["reused"] for result in results], [False, True])
        self.uploader.upload.assert_awaited_once()

    async def test_forgetting_removes_local_history_and_does_not_delete_remote_files(self):
        await self.cache.upload(b"file")
        self.path.with_suffix(".tmp").write_text("old temporary index")
        await self.cache.clear()
        self.assertFalse(self.path.exists())
        self.assertFalse(self.path.with_suffix(".tmp").exists())
        self.assertFalse(self.cache.entries)
        self.assertEqual([call[0] for call in self.uploader.mock_calls], ["upload"])
        self.assertFalse((await self.cache.upload(b"file"))["reused"])

    async def test_save_failure_preserves_successful_upload(self):
        with patch.object(self.cache, "_save", side_effect=OSError("disk full")):
            with self.assertLogs("custompresence.upload_cache", level="WARNING"):
                result = await self.cache.upload(b"file")
        self.assertEqual(result["url"], IMAGE["url"])
        self.assertFalse(result["remembered"])
        self.uploader.upload.assert_awaited_once()

    async def test_invalid_or_untrusted_local_index_is_ignored(self):
        digest = hashlib.sha256(b"file").hexdigest()
        for contents in ("broken json", json.dumps({"images": {
            digest: {"image": IMAGE | {"url": "https://localhost/secret"}, "last_used": 0}
        }})):
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                restored = UploadCache(self.path, self.uploader, check=self.check)
                self.assertFalse(restored.entries)


class AvailabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_only_definite_removal_replaces_a_known_upload(self):
        for status in (200, 301, 403, 404, 410, 429, 500):
            with self.subTest(status=status):
                client = AsyncMock()
                client.head.return_value = httpx.Response(status)
                with patch("custompresence.upload_cache.httpx.AsyncClient") as factory:
                    factory.return_value.__aenter__.return_value = client
                    self.assertEqual(await cached_image_available(IMAGE["url"]), status not in (404, 410))
                client.head.assert_awaited_once_with(IMAGE["url"])

    async def test_temporary_connection_failure_does_not_create_duplicates(self):
        client = AsyncMock()
        client.head.side_effect = httpx.ConnectError("offline")
        with patch("custompresence.upload_cache.httpx.AsyncClient") as factory:
            factory.return_value.__aenter__.return_value = client
            self.assertTrue(await cached_image_available(IMAGE["url"]))

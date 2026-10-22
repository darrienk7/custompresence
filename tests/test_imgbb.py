import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi.testclient import TestClient

from custompresence.api import create_app
from custompresence.images import ImageError, MAX_IMAGE_BYTES
from custompresence.imgbb import ImgBBUploads, UploadError, local_owner_settings
from custompresence.upload_service import create_upload_service
from test_images import png


IMAGE = "https://i.ibb.co/test/example.png"
DELETE = "https://ibb.co/test/deletion-token"


class UploadClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_api_upload_uses_file_bytes_and_keeps_key_out_of_urls(self):
        seen = []
        def handle(request):
            seen.append(request)
            self.assertEqual(str(request.url), "https://api.imgbb.com/1/upload")
            self.assertIn(b"private-test-key", request.content)
            self.assertIn(png(), request.content)
            return httpx.Response(200, json={"success": True, "data": {"url": IMAGE, "delete_url": DELETE}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            uploader = ImgBBUploads(api_key="private-test-key", relay_url="", client=client)
            result = await uploader.upload(png())
        self.assertEqual(result["url"], IMAGE)
        self.assertEqual(result["delete_url"], DELETE)
        self.assertEqual(result["format"], "PNG")
        self.assertNotIn("private-test-key", str(uploader.configuration()))
        self.assertEqual(len(seen), 1)

    async def test_release_service_receives_bytes_without_account_key(self):
        def handle(request):
            self.assertEqual(str(request.url), "https://uploads.example.com/v1/images")
            self.assertEqual(request.content, png())
            self.assertNotIn("authorization", request.headers)
            return httpx.Response(200, json={"url": IMAGE, "delete_url": DELETE})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            uploader = ImgBBUploads(api_key="not-distributed", relay_url="https://uploads.example.com/v1/images", client=client)
            self.assertEqual((await uploader.upload(png()))["url"], IMAGE)

    async def test_missing_config_and_invalid_files_do_not_contact_host(self):
        with self.assertRaisesRegex(UploadError, "configured"):
            await ImgBBUploads(api_key="", relay_url="").upload(png())
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: self.fail("Host should not be called"))) as client:
            with self.assertRaises(ImageError):
                await ImgBBUploads(api_key="test", relay_url="", client=client).upload(b"<svg></svg>")

    async def test_host_failures_and_unsafe_responses_are_reported(self):
        for status, payload, expected in (
            (403, {}, 503), (429, {}, 429), (500, {}, 502),
            (200, {"success": False}, 502),
            (200, {"success": True, "data": {"url": "https://evil.example/image.png"}}, 502),
        ):
            with self.subTest(status=status, payload=payload):
                async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))) as client:
                    with self.assertRaises(UploadError) as error:
                        await ImgBBUploads(api_key="test", relay_url="", client=client).upload(png())
                    self.assertEqual(error.exception.status_code, expected)


class UploadApiTests(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(temporary.cleanup)
        self.settings_path = Path(temporary.name) / "settings.json"

    def test_owner_dotenv_is_read_next_to_source_without_exposing_other_values(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temporary:
            root = Path(temporary)
            package = root / "custompresence"
            package.mkdir()
            (root / ".env").write_text('imgbb_api_key="local-test-key"\nUNRELATED_SECRET=not-read\n', encoding="utf-8-sig")
            with patch("custompresence.imgbb.__file__", str(package / "imgbb.py")), patch("custompresence.imgbb.sys.frozen", False, create=True):
                settings = local_owner_settings()
            self.assertEqual(settings, {"IMGBB_API_KEY": "local-test-key"})

    def test_local_packaged_build_finds_repository_dotenv(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temporary:
            root = Path(temporary)
            binary = root / "dist" / "CustomPresence.exe"
            binary.parent.mkdir(parents=True)
            (root / ".env").write_text("IMGBB_API_KEY=packaged-test-key\n", encoding="utf-8")
            with patch("custompresence.imgbb.sys.executable", str(binary)), patch("custompresence.imgbb.sys.frozen", True, create=True):
                self.assertEqual(local_owner_settings(), {"IMGBB_API_KEY": "packaged-test-key"})

    def test_native_api_authentication_upload_and_size_limit(self):
        uploader = Mock(enabled=True, upload=AsyncMock(return_value={"url": IMAGE, "delete_url": DELETE}))
        app = create_app(self.settings_path, uploader=uploader)
        headers = {"X-Presence-Token": app.state.session_token, "Content-Type": "application/octet-stream"}
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/images", content=png()).status_code, 403)
            result = client.post("/api/images", content=png(), headers=headers)
            self.assertEqual(result.json()["url"], IMAGE)
            uploader.upload.assert_awaited_once_with(png())
            result = client.post("/api/images", content=b"x", headers=headers | {"Content-Length": str(MAX_IMAGE_BYTES + 1)})
            self.assertEqual(result.status_code, 413)

    def test_disabled_upload_has_no_key_or_settings_field(self):
        app = create_app(self.settings_path, uploader=ImgBBUploads(api_key="", relay_url=""))
        headers = {"X-Presence-Token": app.state.session_token}
        with TestClient(app) as client:
            config = client.get("/api/uploads/config", headers=headers).json()
            self.assertFalse(config["enabled"])
            self.assertNotIn("api_key", config)
            self.assertEqual(client.post("/api/images", content=png(), headers=headers).status_code, 503)

    def test_forgetting_upload_history_requires_session_token(self):
        uploader = Mock(enabled=True, upload=AsyncMock(return_value={"url": IMAGE, "delete_url": DELETE}))
        app = create_app(self.settings_path, uploader=uploader)
        headers = {"X-Presence-Token": app.state.session_token, "Content-Type": "application/octet-stream"}
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/images", content=png(), headers=headers).status_code, 200)
            self.assertTrue(app.state.upload_cache.path.exists())
            self.assertEqual(client.delete("/api/images/cache").status_code, 403)
            self.assertTrue(app.state.upload_cache.path.exists())
            self.assertEqual(client.delete("/api/images/cache", headers=headers).status_code, 200)
            self.assertFalse(app.state.upload_cache.path.exists())
        uploader.upload.assert_awaited_once()

    def test_public_service_forwards_uploads_and_enforces_rate_limit(self):
        uploader = Mock(enabled=True, upload=AsyncMock(return_value={"url": IMAGE}))
        with TestClient(create_upload_service(uploader)) as client:
            self.assertEqual(client.get("/health").json(), {"ready": True})
            for _ in range(6):
                self.assertEqual(client.post("/v1/images", content=png()).status_code, 200)
            self.assertEqual(client.post("/v1/images", content=png()).status_code, 429)
        self.assertEqual(uploader.upload.await_count, 6)

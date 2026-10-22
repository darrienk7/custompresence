import asyncio
import unittest
from io import BytesIO
from unittest.mock import patch

import httpx
from PIL import Image

from custompresence.images import ImageError, check_image_url, inspect_image, normalize_image_url, public_target
from custompresence.models import Activity


def png():
    output = BytesIO()
    Image.new("RGB", (64, 64), "#8c83ff").save(output, "PNG")
    return output.getvalue()


async def mock_target(url):
    return httpx.URL(url), httpx.URL(url).host


class LinkTests(unittest.TestCase):
    def test_giphy_share_and_embed_links_become_gifs(self):
        for link in ("https://giphy.com/gifs/funny-cat-ICOgUNjpvO0PC", "https://giphy.com/embed/ICOgUNjpvO0PC"):
            self.assertEqual(normalize_image_url(link), "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif")
        self.assertEqual(Activity(image="https://giphy.com/gifs/funny-cat-ICOgUNjpvO0PC").image,
                         "https://media.giphy.com/media/ICOgUNjpvO0PC/giphy.gif")

    def test_imgur_image_links_convert_but_albums_do_not(self):
        self.assertEqual(normalize_image_url("https://imgur.com/abc123"), "https://i.imgur.com/abc123.png")
        self.assertEqual(normalize_image_url("https://imgur.com/abc123.gifv"), "https://i.imgur.com/abc123.gif")
        self.assertEqual(normalize_image_url("https://i.imgur.com/abc123.gifv?x=1"), "https://i.imgur.com/abc123.gif?x=1")
        for link in ("https://imgur.com/a/abc123", "https://imgur.com/gallery/a-cat-abc123",
                     "https://giphy.com/clips/cat-123", "https://user:password@example.com/image.png",
                     "https://example.com:8443/image.png", "http://example.com/image.png"):
            with self.subTest(link=link):
                with self.assertRaises(ValueError):
                    normalize_image_url(link)

    def test_file_content_is_checked_and_size_is_reported(self):
        self.assertEqual(inspect_image(png()), {"format": "PNG", "width": 64, "height": 64})
        for data in (b"<html>not an image</html>", b"<svg></svg>", b"GIF89a broken"):
            with self.assertRaises(ImageError):
                inspect_image(data)


class NetworkLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_checks_actual_image_bytes_not_just_extension(self):
        with httpx.MockTransport(lambda request: httpx.Response(200, content=png(), headers={"Content-Type": "image/png"})) as transport:
            async with httpx.AsyncClient(transport=transport) as client:
                result = await check_image_url("https://imgur.com/abc123", client=client, target=mock_target)
        self.assertEqual(result["url"], "https://i.imgur.com/abc123.png")
        self.assertTrue(result["converted"])
        self.assertEqual(result["width"], 64)

    async def test_html_and_missing_images_explain_the_problem(self):
        for status, content_type, message in ((200, "text/html", "webpage"), (404, "image/png", "HTTP 404")):
            with httpx.MockTransport(lambda request: httpx.Response(status, content=png(), headers={"Content-Type": content_type})) as transport:
                async with httpx.AsyncClient(transport=transport) as client:
                    with self.assertRaisesRegex(ImageError, message):
                        await check_image_url("https://example.com/image.png", client=client, target=mock_target)

    async def test_redirect_targets_are_rechecked(self):
        seen = []
        async def target(url):
            seen.append(url)
            if "127.0.0.1" in url:
                raise ImageError(422, "private address")
            return await mock_target(url)
        with httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"})) as transport:
            async with httpx.AsyncClient(transport=transport) as client:
                with self.assertRaisesRegex(ImageError, "private address"):
                    await check_image_url("https://example.com/image.png", client=client, target=target)
        self.assertEqual(len(seen), 2)

    async def test_imgur_removed_placeholder_is_not_treated_as_success(self):
        with httpx.MockTransport(lambda request: httpx.Response(302, headers={"Location": "https://i.imgur.com/removed.png"})) as transport:
            async with httpx.AsyncClient(transport=transport) as client:
                with self.assertRaisesRegex(ImageError, "removed"):
                    await check_image_url("https://i.imgur.com/old.png", client=client, target=mock_target)

    async def test_tenor_page_metadata_is_resolved_to_the_actual_gif(self):
        def handle(request):
            if request.url.host == "tenor.com":
                return httpx.Response(200, text='<meta property="og:image" content="https://media1.tenor.com/m/test/cat.gif">', headers={"Content-Type":"text/html"})
            return httpx.Response(200, content=png(), headers={"Content-Type":"image/png"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            result = await check_image_url("https://tenor.com/view/cat-gif-123", client=client, target=mock_target)
        self.assertEqual(result["url"], "https://media1.tenor.com/m/test/cat.gif")
        self.assertTrue(result["converted"])

    async def test_public_address_is_pinned_and_private_dns_is_rejected(self):
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 443))]):
            pinned, hostname = await public_target("https://example.com/image.png")
        self.assertEqual(pinned.host, "93.184.216.34")
        self.assertEqual(hostname, "example.com")
        for ip in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"):
            with patch.object(loop, "getaddrinfo", return_value=[(2, 1, 6, "", (ip, 443))]):
                with self.assertRaises(ImageError):
                    await public_target("https://example.com/image.png")

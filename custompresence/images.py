"""Convert common sharing links and check bounded, public image downloads."""

import asyncio
import ipaddress
import socket
import warnings
from html.parser import HTMLParser
from io import BytesIO
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 8 * 1024 * 1024
FORMATS = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"),
           "GIF": ("gif", "image/gif"), "WEBP": ("webp", "image/webp"), "AVIF": ("avif", "image/avif")}


class TenorImage(HTMLParser):
    def __init__(self):
        super().__init__()
        self.url = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property") == "og:image":
            candidate = attrs.get("content", "")
            host = urlsplit(candidate).hostname or ""
            if host in {"media.tenor.com", "c.tenor.com"} or (host.startswith("media") and host.endswith(".tenor.com")
                                                              and host[5:-10].isdigit()):
                self.url = normalize_image_url(candidate)


class ImageError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code


def normalize_image_url(value):
    value = value.strip()
    try:
        parts = urlsplit(value)
        if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
                or parts.port not in (None, 443) or len(value) > 2048):
            raise ValueError
    except ValueError as exc:
        raise ValueError("Use a public HTTPS image link.") from exc
    host = parts.hostname.lower()
    segments = [unquote(s) for s in parts.path.split("/") if s]
    if host in {"giphy.com", "www.giphy.com"}:
        if len(segments) != 2 or segments[0] not in {"gifs", "media", "embed"}:
            raise ValueError("Use a Giphy GIF link, rather than a profile, search, or video page.")
        image_id = segments[1].rsplit("-", 1)[-1]
        if not image_id.isascii() or not image_id.isalnum():
            raise ValueError("This Giphy link does not contain a valid GIF ID.")
        return f"https://media.giphy.com/media/{image_id}/giphy.gif"
    if host in {"imgur.com", "www.imgur.com", "m.imgur.com"}:
        if len(segments) != 1:
            raise ValueError("Imgur album/gallery links contain a webpage. Copy one image's address instead.")
        identifier, _, extension = segments[0].partition(".")
        if not identifier.isascii() or not identifier.isalnum():
            raise ValueError("Use a single-image Imgur link.")
        extension = extension.lower() or "png"
        if extension == "gifv":
            extension = "gif"
        if extension not in {"png", "jpg", "jpeg", "gif", "webp", "avif"}:
            raise ValueError("Use an image or GIF, rather than a video link.")
        return f"https://i.imgur.com/{identifier}.{extension}"
    if host == "i.imgur.com" and parts.path.lower().endswith(".gifv"):
        return value.replace(parts.path, parts.path[:-1], 1)
    return value


def inspect_image(data):
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ImageError(413, "Choose an image or GIF up to 8 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in FORMATS:
                    raise ImageError(415, "Choose PNG, JPG, GIF, WebP, or AVIF.")
                width, height = image.size
                if width * height > 16_777_216 or max(width, height) > 8192:
                    raise ImageError(413, "Use an image no larger than 8192 pixels per side and 16 megapixels.")
                result = {"format": image.format, "width": width, "height": height}
                image.verify()
                return result
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as exc:
        raise ImageError(415, "The file or link is not a supported image. Share pages and MP4 videos won't work.") from exc


async def public_target(url):
    """Pin the connection to a checked public address, retaining TLS SNI/Host."""
    parts = urlsplit(url)
    try:
        addresses = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM), timeout=8)
    except (OSError, TimeoutError) as exc:
        raise ImageError(422, "The image host could not be reached. Check the link and try again.") from exc
    ips = list(dict.fromkeys(address[4][0] for address in addresses))
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
        raise ImageError(422, "Use a publicly reachable image host, rather than a local or private address.")
    return httpx.URL(url).copy_with(host=ips[0]), parts.hostname


async def check_image_url(value, *, client=None, target=public_target):
    try:
        url = normalize_image_url(value)
    except ValueError as exc:
        raise ImageError(422, str(exc)) from exc
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False)
    try:
        for _ in range(4):
            if urlsplit(url).hostname == "i.imgur.com" and urlsplit(url).path.lower() in {"/removed.png", "/removed.jpg", "/removed.gif"}:
                raise ImageError(422, "Imgur has removed this image. Choose another image or upload your own file.")
            pinned, hostname = await target(url)
            async with client.stream("GET", pinned, headers={"Host": hostname, "User-Agent": "CustomPresence/0.1",
                                                           "Accept": "image/*", "Accept-Encoding": "identity"},
                                     extensions={"sni_hostname": hostname}) as response:
                if response.is_redirect:
                    try:
                        url = normalize_image_url(urljoin(url, response.headers.get("location", "")))
                    except ValueError as exc:
                        raise ImageError(422, "The image redirects to an unsupported address.") from exc
                    continue
                if response.status_code != 200:
                    raise ImageError(422, f"The image host returned HTTP {response.status_code}. Try a different direct image link.")
                if not response.headers.get("content-type", "").lower().startswith("image/"):
                    if urlsplit(url).hostname not in {"tenor.com", "www.tenor.com"} or not urlsplit(url).path.startswith("/view/"):
                        raise ImageError(422, "This link opens a webpage or video. Copy the image address instead of the page link.")
                    html = bytearray()
                    async for chunk in response.aiter_bytes(65536):
                        html.extend(chunk)
                        if len(html) > 1_048_576:
                            raise ImageError(422, "This Tenor page is too large to check. Copy its image address instead.")
                    parser = TenorImage()
                    try:
                        parser.feed(html.decode("utf-8", errors="replace"))
                    except ValueError as exc:
                        raise ImageError(422, "This Tenor page does not provide a usable GIF link.") from exc
                    if not parser.url:
                        raise ImageError(422, "This Tenor page does not provide a usable GIF link. Copy its image address instead.")
                    url = parser.url
                    continue
                data = bytearray()
                async for chunk in response.aiter_bytes(65536):
                    data.extend(chunk)
                    if len(data) > MAX_IMAGE_BYTES:
                        raise ImageError(413, "The linked image is over 8 MB. Choose a smaller version.")
                info = await asyncio.to_thread(inspect_image, bytes(data))
                return {"url": url, **info, "converted": url != value.strip()}
        raise ImageError(422, "The image host redirected too many times. Try another direct image link.")
    except httpx.HTTPError as exc:
        raise ImageError(422, "The image host could not be reached securely. Try another link or upload the file.") from exc
    finally:
        if owns_client:
            await client.aclose()

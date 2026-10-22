"""Optional shared upload backend: the ImgBB key stays on its host."""

import asyncio
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request

from .images import MAX_IMAGE_BYTES, ImageError
from .imgbb import ImgBBUploads


async def read_image_body(request):
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(400, "Invalid file size.") from exc
    if length > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Choose an image or GIF up to 8 MB.")
    data = bytearray()
    try:
        async with asyncio.timeout(20):
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_IMAGE_BYTES:
                    raise HTTPException(413, "Choose an image or GIF up to 8 MB.")
    except TimeoutError as exc:
        raise HTTPException(408, "Receiving the file took too long. Try again.") from exc
    return bytes(data)


def create_upload_service(uploader=None):
    uploader = uploader if uploader is not None else ImgBBUploads(relay_url="")
    app = FastAPI(title="Custom Presence uploads", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.uploader = uploader
    recent = defaultdict(deque)
    active = asyncio.Semaphore(2)

    @app.get("/health")
    def health():
        return {"ready": uploader.enabled}

    @app.post("/v1/images")
    async def upload(request: Request):
        if not uploader.enabled:
            raise HTTPException(503, "Uploads are not configured.")
        now = time.monotonic()
        for key in list(recent):
            while recent[key] and recent[key][0] <= now - 60:
                recent[key].popleft()
            if not recent[key]:
                del recent[key]
        ip = request.client.host if request.client else "unknown"
        if len(recent) >= 2048 or len(recent[ip]) >= 6 or active.locked():
            raise HTTPException(429, "Too many uploads. Please wait and try again.")
        recent[ip].append(now)
        async with active:
            data = await read_image_body(request)
            try:
                return await uploader.upload(data)
            except ImageError as exc:
                raise HTTPException(exc.status_code, str(exc)) from exc

    return app

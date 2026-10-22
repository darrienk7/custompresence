import asyncio
import logging
import json
import secrets
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pypresence import Presence as DiscordPresence
from pypresence.types import ActivityType, StatusDisplayType
from platformdirs import user_data_path
from pydantic import BaseModel, Field

from .config import APPLICATION_ID
from .models import Activity, INVITE_FIELDS
from .imgbb import ImgBBUploads
from .images import ImageError, check_image_url
from .upload_service import read_image_body
from .upload_cache import UploadCache


logger = logging.getLogger(__name__)


class ImageLink(BaseModel):
    url: str = Field(min_length=1, max_length=2048)


class Presence(DiscordPresence):
    async def handshake(self):
        # pypresence times out opening IPC, but not the subsequent handshake read.
        return await asyncio.wait_for(super().handshake(), timeout=self.connection_timeout)


class DiscordConnection:
    # All synchronous RPC operations share one thread and one asyncio loop.
    def __init__(self):
        self.rpc = None
        self.application_id = APPLICATION_ID
        self.loop = None
        self.automatic_party_id = uuid4().hex

    def stop(self):
        if self.rpc is not None:
            rpc, self.rpc = self.rpc, None
            try:
                rpc.clear()
            finally:
                try:
                    rpc.close()
                finally:
                    self._close_loop()

    def _close_loop(self):
        if self.loop is not None:
            if not self.loop.is_closed():
                self.loop.close()
            self.loop = None
            asyncio.set_event_loop(None)

    def update(self, activity):
        if self.rpc is None:
            self.stop()
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            rpc = None
            try:
                rpc = Presence(self.application_id, connection_timeout=5, response_timeout=5)
                rpc.connect()
            except Exception:
                try:
                    if rpc is not None:
                        rpc.close()
                except Exception:
                    pass
                finally:
                    self._close_loop()
                raise
            self.rpc = rpc
        try:
            fields = activity.rpc_fields()
            if fields["party_size"] is not None and not fields["party_id"]:
                fields["party_id"] = self.automatic_party_id
            self.rpc.update(activity_type=ActivityType[activity.activity_type.upper()],
                            status_display_type=StatusDisplayType[activity.status_display_type.upper()],
                            **fields)
        except Exception:
            try:
                self.stop()
            except Exception:
                pass
            raise


def create_app(settings_path: Path | None = None, uploader: ImgBBUploads | None = None):
    if settings_path is None:
        settings_path = user_data_path("CustomPresence", appauthor=False) / "settings.json"
    connection = DiscordConnection()
    uploader = uploader if uploader is not None else ImgBBUploads()
    upload_cache = UploadCache(settings_path.with_name("uploads.json"), uploader)
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        app.state.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="discord")
        try:
            yield
        finally:
            try:
                await asyncio.get_running_loop().run_in_executor(app.state.worker, connection.stop)
            except Exception:
                logger.exception("Could not clear activity during shutdown")
            finally:
                app.state.worker.shutdown(wait=True)

    app = FastAPI(title="Custom Presence", lifespan=lifespan)
    app.state.connection = connection
    app.state.session_token = token
    app.state.uploader = uploader
    app.state.upload_cache = upload_cache
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def local_requests(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            if (origin and origin != str(request.base_url).rstrip("/")) or not secrets.compare_digest(
                request.headers.get("x-presence-token", ""), token
            ):
                return JSONResponse({"detail": "Open this app directly to change your activity."}, status_code=403,
                                    headers={"Cache-Control": "no-store"})
        response = await call_next(request)
        # Settings and bundled scripts must reflect this launch, never a prior browser session.
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def index():
        html = files("custompresence").joinpath("assets/index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__SESSION_TOKEN__", token), headers={"Cache-Control": "no-store"})

    @app.get("/assets/{filename}", include_in_schema=False)
    def asset(filename: str):
        if filename not in {"app.css", "app.js"}:
            raise HTTPException(404)
        content = files("custompresence").joinpath("assets", filename).read_text(encoding="utf-8")
        return HTMLResponse(content, media_type="text/css" if filename.endswith(".css") else "text/javascript")

    @app.get("/terms", include_in_schema=False)
    @app.get("/privacy", include_in_schema=False)
    @app.get("/terms.html", include_in_schema=False)
    @app.get("/privacy.html", include_in_schema=False)
    def policy(request: Request):
        name = request.url.path.strip("/").removesuffix(".html") + ".html"
        content = files("custompresence").joinpath("assets/legal", name).read_text(encoding="utf-8")
        return HTMLResponse(content)

    @app.get("/api/settings")
    def settings():
        try:
            saved = json.loads(settings_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict):
                return {}
            if saved.get("_schema_version") != 2 and saved.get("name") == "Custom Presence":
                saved["name"] = ""
            return Activity.model_validate(saved).model_dump(exclude=INVITE_FIELDS)
        except (OSError, ValueError):
            return {}

    @app.delete("/api/settings")
    def reset_settings():
        try:
            settings_path.unlink(missing_ok=True)
        except OSError as exc:
            raise HTTPException(503, "Saved settings could not be removed. Try again after restarting the app.") from exc
        return {"message": "Saved settings removed."}

    @app.get("/api/uploads/config")
    def upload_config():
        return uploader.configuration()

    @app.post("/api/images")
    async def upload_image(request: Request):
        if not uploader.enabled:
            raise HTTPException(503, "Uploads aren't configured in this build yet. You can paste a public image link.")
        data = await read_image_body(request)
        try:
            return await upload_cache.upload(data)
        except ImageError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    @app.delete("/api/images/cache")
    async def forget_uploads():
        try:
            await upload_cache.clear()
        except OSError as exc:
            raise HTTPException(503, "Remembered uploads could not be removed. Try again after restarting the app.") from exc
        return {"message": "Upload history cleared. Hosted images remain online."}

    @app.post("/api/images/check")
    async def check_image(link: ImageLink):
        try:
            return await check_image_url(link.url)
        except ImageError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    def save_settings(activity):
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = settings_path.with_suffix(".tmp")
        saved = {"_schema_version": 2, **activity.model_dump(mode="json", exclude=INVITE_FIELDS)}
        temp_path.write_text(json.dumps(saved, indent=2), encoding="utf-8")
        temp_path.replace(settings_path)

    @app.post("/api/activity")
    async def update(activity: Activity):
        try:
            await asyncio.get_running_loop().run_in_executor(app.state.worker, connection.update, activity)
        except Exception as exc:
            raise HTTPException(503, f"Discord could not update your activity ({type(exc).__name__}). "
                                "Make sure Discord desktop is running and try again.") from exc
        try:
            await asyncio.get_running_loop().run_in_executor(app.state.worker, save_settings, activity)
        except OSError:
            logger.exception("Could not save activity settings")
            return {"message": "Activity updated, but settings could not be saved for next time."}
        return {"message": "Activity updated. Check your Discord profile."}

    @app.delete("/api/activity")
    async def stop():
        try:
            await asyncio.get_running_loop().run_in_executor(app.state.worker, connection.stop)
        except Exception as exc:
            raise HTTPException(503, "Discord disconnected. Reopen Discord and apply your activity again.") from exc
        return {"message": "Activity cleared."}

    return app


def main():
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=8000, access_log=False)

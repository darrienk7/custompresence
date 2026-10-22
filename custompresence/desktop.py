"""Own the native window and the lifetime of its local FastAPI server."""

import logging
import socket
import sys
import threading
import time
from importlib.resources import as_file, files

import uvicorn
from platformdirs import user_log_path

from .api import create_app


logger = logging.getLogger(__name__)


class LocalServer:
    def __init__(self, app):
        self.server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=0, log_config=None, access_log=False,
            http="h11", ws="none", loop="asyncio", timeout_graceful_shutdown=10,
        ))
        self.thread = None
        self.socket = None
        self.error = None

    def _run(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as exc:
            self.error = exc
            logger.exception("Local server failed")

    def start(self, timeout=15):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.bind(("127.0.0.1", 0))
            port = self.socket.getsockname()[1]
            self.thread = threading.Thread(target=self._run, name="presence-server", daemon=True)
            self.thread.start()
            deadline = time.monotonic() + timeout
            while not self.server.started:
                if not self.thread.is_alive():
                    raise RuntimeError("The local server could not start.") from self.error
                if time.monotonic() >= deadline:
                    raise TimeoutError("The local server took too long to start.")
                time.sleep(0.02)
            return f"http://127.0.0.1:{port}"
        except BaseException:
            self.stop()
            raise

    def stop(self):
        self.server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=25)
            if self.thread.is_alive():
                raise RuntimeError("The local server did not stop in time.")
        if self.socket is not None:
            self.socket.close()
            self.socket = None


def show_startup_error(message):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, "Custom Presence", 0x10)
    elif sys.platform == "darwin":
        from AppKit import NSAlert
        alert = NSAlert.alloc().init()
        alert.setMessageText_("Custom Presence could not start")
        alert.setInformativeText_(message)
        alert.runModal()


def main():
    log_dir = user_log_path("CustomPresence", appauthor=False)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "desktop.log"
    logging.basicConfig(filename=log_path, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if sys.platform == "win32":
        import ctypes
        # Keep Windows taskbar grouping separate from Python and other webview apps.
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CustomPresence.Desktop")
        if result:
            logger.warning("Windows could not set the app identity (%s)", result)
    server = LocalServer(create_app())
    try:
        # Import and start the GUI on the main thread, after configuring file logs.
        import webview
        url = server.start()
        webview.create_window("Custom Presence", url, width=960, height=850,
                              min_size=(560, 650), background_color="#111216", text_select=False)
        icon_name = "app.ico" if sys.platform == "win32" else "app.png"
        with as_file(files("custompresence").joinpath("assets/icons", icon_name)) as icon:
            # Preferences live in our JSON files; browser history must not restore old form values.
            webview.start(private_mode=True, icon=str(icon))
    except Exception:
        logger.exception("Desktop startup failed")
        show_startup_error(f"Please try reopening the app. On Windows, make sure Microsoft Edge "
                           f"WebView2 Runtime is installed.\n\nDetails: {log_path}")
    finally:
        server.stop()

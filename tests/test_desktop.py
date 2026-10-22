import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.request import ProxyHandler, build_opener

from custompresence.api import create_app
from custompresence.desktop import LocalServer, main


class DesktopTests(unittest.TestCase):
    def test_server_starts_on_available_port_and_stops(self):
        server = LocalServer(create_app())
        try:
            url = server.start()
            self.assertTrue(url.startswith("http://127.0.0.1:"))
            opener = build_opener(ProxyHandler({}))
            with opener.open(url, timeout=5) as response:
                self.assertIn(b"Custom Presence", response.read())
        finally:
            server.stop()
        self.assertFalse(server.thread.is_alive())
        self.assertIsNone(server.socket)

    def test_startup_failure_does_not_leave_server_running(self):
        server = LocalServer(create_app())
        with patch.object(server.server, "run", side_effect=RuntimeError("startup failed")):
            with self.assertLogs("custompresence.desktop", level="ERROR"):
                with self.assertRaises(RuntimeError):
                    server.start()
        self.assertFalse(server.thread.is_alive())
        self.assertIsNone(server.socket)

    def test_window_exit_always_stops_server(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=build) as temp:
            directory = Path(temp)
            for error in (None, RuntimeError("window failed")):
                with self.subTest(error=error):
                    webview = Mock()
                    webview.start.side_effect = error
                    with (patch.dict("sys.modules", {"webview": webview}),
                          patch("custompresence.desktop.LocalServer") as factory,
                          patch("custompresence.desktop.user_log_path", return_value=directory),
                          patch("custompresence.desktop.logging.basicConfig"),
                          patch("custompresence.desktop.logger"),
                          patch("custompresence.desktop.show_startup_error")):
                        factory.return_value.start.return_value = "http://127.0.0.1:12345"
                        main()
                        webview.create_window.assert_called_once()
                        icon = Path(webview.start.call_args.kwargs["icon"])
                        self.assertTrue(icon.is_file())
                        self.assertIn(icon.suffix, {".ico", ".png"})
                        self.assertTrue(webview.start.call_args.kwargs["private_mode"])
                        self.assertNotIn("storage_path", webview.start.call_args.kwargs)
                        factory.return_value.stop.assert_called_once()

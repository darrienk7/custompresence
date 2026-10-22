import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from pypresence.types import ActivityType, StatusDisplayType

from custompresence.api import Activity, DiscordConnection, create_app
from custompresence.config import APPLICATION_ID


class AppTests(unittest.TestCase):
    def setUp(self):
        build = Path(__file__).resolve().parents[1] / "build"
        build.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=build)
        self.addCleanup(temp.cleanup)
        self.settings_path = Path(temp.name) / "settings.json"
        self.app = create_app(self.settings_path)
        self.manager = self.app.state.connection
        self.client = self.enterContext(TestClient(self.app))
        self.headers = {"X-Presence-Token": self.app.state.session_token}
        self.payload = {"name": "My activity",
                        "image": "https://example.com/art.gif"}

    def test_interface_includes_session_token(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.app.state.session_token, response.text)
        self.assertNotIn("__SESSION_TOKEN__", response.text)
        self.assertNotIn("application_id", response.text)
        self.assertNotIn("Developer Portal", response.text)

    def test_settings_and_editor_assets_cannot_be_replayed_from_browser_cache(self):
        import json
        for path in ("/", "/assets/app.js", "/assets/app.css", "/api/settings"):
            response = self.client.get(path, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
        self.settings_path.write_text(json.dumps(self.payload), encoding="utf-8")
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).json()["image"], self.payload["image"])
        self.settings_path.write_text(json.dumps(self.payload | {"image": ""}), encoding="utf-8")
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).json()["image"], "")

    def test_old_settings_migrate_without_showing_application_id(self):
        import json
        self.settings_path.write_text(json.dumps(self.payload | {"application_id": "123456789012345678"}), encoding="utf-8")
        saved = self.client.get("/api/settings", headers=self.headers).json()
        self.assertEqual(saved["name"], self.payload["name"])
        self.assertEqual(saved["activity_type"], "playing")
        self.assertNotIn("application_id", saved)

    def test_apply_and_restore_across_launches(self):
        self.payload["activity_type"] = "listening"
        with patch.object(self.manager, "update") as update:
            response = self.client.post("/api/activity", json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.args[0].name, "My activity")
        second_app = create_app(self.settings_path)
        with TestClient(second_app) as client:
            response = client.get("/api/settings", headers={"X-Presence-Token": second_app.state.session_token})
            self.assertEqual(response.json()["image"], self.payload["image"])
            self.assertEqual(response.json()["activity_type"], "listening")

    def test_discord_unavailable(self):
        with patch.object(self.manager, "update", side_effect=ConnectionError):
            response = self.client.post("/api/activity", json=self.payload, headers=self.headers)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.settings_path.exists())

    def test_clear(self):
        with patch.object(self.manager, "stop") as stop:
            self.assertEqual(self.client.delete("/api/activity", headers=self.headers).status_code, 200)
            stop.assert_called_once()

    def test_validation(self):
        with patch.object(self.manager, "update") as update:
            for changes in ({"name": "x" * 129}, {"image": "file:///a.gif"}, {"activity_type": "streaming"}):
                self.assertEqual(self.client.post("/api/activity", json=self.payload | changes,
                                                 headers=self.headers).status_code, 422)
            update.assert_not_called()

    def test_foreign_origin_and_missing_token_blocked(self):
        with patch.object(self.manager, "update") as update:
            self.assertEqual(self.client.post("/api/activity", json=self.payload,
                             headers=self.headers | {"Origin": "https://other.example"}).status_code, 403)
            self.assertEqual(self.client.post("/api/activity", json=self.payload).status_code, 403)
            self.assertEqual(self.client.get("/api/settings").status_code, 403)
            update.assert_not_called()

    def test_corrupt_settings_do_not_break_startup(self):
        self.settings_path.write_text("invalid json", encoding="utf-8")
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).json(), {})

    def test_shutdown_clears_activity(self):
        other_app = create_app(self.settings_path)
        with patch.object(other_app.state.connection, "stop") as stop:
            with TestClient(other_app):
                pass
            stop.assert_called_once()

    @patch("custompresence.api.Presence")
    def test_rpc_payload_and_reuse(self, presence):
        manager = DiscordConnection()
        activity = Activity(**self.payload)
        manager.update(activity)
        manager.update(activity)
        presence.assert_called_once_with(APPLICATION_ID, connection_timeout=5, response_timeout=5)
        presence.return_value.update.assert_called_with(activity_type=ActivityType.PLAYING,
                                                        status_display_type=StatusDisplayType.NAME,
                                                        **activity.rpc_fields())
        loop = manager.loop
        manager.stop()
        presence.return_value.clear.assert_called_once()
        presence.return_value.close.assert_called_once()
        self.assertTrue(loop.is_closed())

    @patch("custompresence.api.Presence")
    def test_activity_selection_reaches_discord(self, presence):
        manager = DiscordConnection()
        try:
            for kind, expected in (("playing", ActivityType.PLAYING), ("listening", ActivityType.LISTENING),
                                   ("watching", ActivityType.WATCHING), ("competing", ActivityType.COMPETING)):
                with self.subTest(kind=kind):
                    manager.update(Activity(**self.payload, activity_type=kind))
                    self.assertEqual(presence.return_value.update.call_args.kwargs["activity_type"], expected)
        finally:
            manager.stop()

    @patch("custompresence.api.Presence")
    def test_party_without_optional_fields_has_a_stable_id_and_visible_state(self, presence):
        from pypresence.payloads import Payload
        manager = DiscordConnection()
        activity = Activity(party_current=2, party_max=4)
        try:
            manager.update(activity)
            first = presence.return_value.update.call_args.kwargs
            manager.update(activity)
            second = presence.return_value.update.call_args.kwargs
            self.assertTrue(first["party_id"])
            self.assertEqual(first["party_id"], second["party_id"])
            payload = Payload.set_activity(**second).data["args"]["activity"]
            self.assertEqual(payload["party"], {"id": first["party_id"], "size": [2, 4]})
            self.assertEqual(payload["state"], "In a party")
            self.assertEqual(activity.state, "")
            self.assertEqual(activity.party_id, "")
            manager.update(Activity())
            cleared = presence.return_value.update.call_args.kwargs
            self.assertIsNone(cleared["state"])
            self.assertIsNone(cleared["party_id"])
            self.assertIsNone(cleared["party_size"])
        finally:
            manager.stop()

    def test_party_text_fallback_for_other_activity_types(self):
        for kind in ("listening", "watching", "competing"):
            for state in ("", "With friends"):
                with self.subTest(kind=kind, state=state):
                    activity = Activity(activity_type=kind, state=state, party_current=2, party_max=4)
                    self.assertEqual(activity.rpc_fields()["state"], (state or "In a party") + " (2 of 4)")
                    self.assertEqual(activity.state, state)
        self.assertEqual(Activity(state="With friends", party_current=2, party_max=4).rpc_fields()["state"], "With friends")
        self.assertEqual(Activity(party_current=2, party_max=4, status_display_type="state").rpc_fields()["state"], "In a party")

    def test_party_text_fallback_keeps_counts_within_discord_text_limit(self):
        for text in ("x" * 128, "🎮" * 64):
            activity = Activity(activity_type="watching", state=text, party_current=2, party_max=4)
            sent = activity.rpc_fields()["state"]
            self.assertLessEqual(len(sent.encode("utf-16-le")), 256)
            self.assertTrue(sent.endswith("… (2 of 4)"))
            self.assertEqual(activity.state, text)

    @patch("custompresence.api.Presence")
    def test_client_cannot_override_bundled_application_id(self, presence):
        manager = DiscordConnection()
        try:
            manager.update(Activity(**(self.payload | {"application_id": "123456789012345678"})))
            self.assertEqual(presence.call_args.args[0], APPLICATION_ID)
        finally:
            manager.stop()

    @patch("custompresence.api.Presence")
    def test_failed_connect_closes_loop(self, presence):
        presence.return_value.connect.side_effect = ConnectionError
        manager = DiscordConnection()
        with self.assertRaises(ConnectionError):
            manager.update(Activity(**self.payload))
        self.assertIsNone(manager.loop)
        self.assertIsNone(manager.rpc)

    def test_basic_activity_defaults_to_blank_name(self):
        with patch.object(self.manager, "update") as update:
            response = self.client.post("/api/activity", json={"activity_type": "watching"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.args[0].name, "")

    def test_blank_activity_is_preserved_and_uses_a_space_for_discord(self):
        for name in ("", "   "):
            with patch.object(self.manager, "update") as update:
                response = self.client.post("/api/activity", json=self.payload | {"name": name}, headers=self.headers)
            self.assertEqual(response.status_code, 200)
            activity = update.call_args.args[0]
            self.assertEqual(activity.name, "")
            self.assertEqual(activity.rpc_fields()["name"], " ")
            self.assertEqual(self.client.get("/api/settings", headers=self.headers).json()["name"], "")

    def test_old_default_name_becomes_empty_but_explicit_names_are_kept(self):
        self.settings_path.write_text(Activity(name="Custom Presence", image=self.payload["image"]).model_dump_json(), encoding="utf-8")
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).json()["name"], "")
        with patch.object(self.manager, "update"):
            response = self.client.post("/api/activity", json=self.payload | {"name": "Custom Presence"}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/settings", headers=self.headers).json()["name"], "Custom Presence")

    @patch("custompresence.api.Presence")
    def test_advanced_fields_reach_discord(self, presence):
        manager = DiscordConnection()
        try:
            manager.update(Activity(**(self.payload | {
                "details": "Capture the Flag", "state": "In a match", "status_display_type": "state",
                "details_url": "https://example.com/mode", "state_url": "https://example.com/match",
                "large_text": "Map", "large_url": "https://example.com/map",
                "small_image": "icon_key", "small_text": "Character", "small_url": "https://example.com/character",
                "start": 1800000000, "end": 1800003600,
                "party_id": "my-party", "party_current": 2, "party_max": 4,
                "join": "join-token", "spectate": "spectate-token", "match": "match-token",
                "buttons": [{"label": "Website", "url": "https://example.com"}], "instance": False,
            })))
            fields = presence.return_value.update.call_args.kwargs
            self.assertEqual(fields["status_display_type"], StatusDisplayType.STATE)
            self.assertEqual(fields["party_size"], [2, 4])
            self.assertEqual(fields["party_id"], "my-party")
            self.assertEqual(fields["start"], 1800000000)
            self.assertEqual(fields["end"], 1800003600)
            self.assertEqual(fields["small_image"], "icon_key")
            self.assertEqual(fields["small_url"], "https://example.com/character")
            self.assertEqual(fields["join"], "join-token")
            self.assertEqual(fields["buttons"], [{"label": "Website", "url": "https://example.com"}])
            self.assertFalse(fields["instance"])
        finally:
            manager.stop()

    def test_invalid_advanced_settings_never_reach_discord(self):
        invalid = (
            {"party_current": 2}, {"party_current": 5, "party_max": 4},
            {"start": 200, "end": 100}, {"start": -1}, {"status_display_type": "details"},
            {"details_url": "javascript:alert(1)"}, {"small_image": "file:///local.png"},
            {"buttons": [{"label": "Website", "url": "http://example.com"}]},
            {"buttons": [{"label": "Website", "url": "https://example.com"}] * 3},
        )
        with patch.object(self.manager, "update") as update:
            for changes in invalid:
                with self.subTest(changes=changes):
                    response = self.client.post("/api/activity", json=self.payload | changes, headers=self.headers)
                    self.assertEqual(response.status_code, 422)
            update.assert_not_called()

    def test_invite_tokens_are_sent_but_not_saved_or_restored(self):
        payload = self.payload | {"join": "private-join", "spectate": "private-spectate", "match": "private-match"}
        with patch.object(self.manager, "update") as update:
            response = self.client.post("/api/activity", json=payload, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(update.call_args.args[0].join, "private-join")
        saved = self.settings_path.read_text(encoding="utf-8")
        self.assertNotIn("private-", saved)
        self.settings_path.write_text(Activity(**payload).model_dump_json(), encoding="utf-8")
        restored = self.client.get("/api/settings", headers=self.headers).json()
        self.assertNotIn("join", restored)
        self.assertNotIn("spectate", restored)
        self.assertNotIn("match", restored)

    def test_reset_removes_settings_without_contacting_discord(self):
        self.settings_path.write_text("{}", encoding="utf-8")
        with patch.object(self.manager, "stop") as stop:
            response = self.client.delete("/api/settings", headers=self.headers)
            self.assertEqual(response.status_code, 200)
            self.assertFalse(self.settings_path.exists())
            self.assertEqual(self.client.get("/api/settings", headers=self.headers).json(), {})
            stop.assert_not_called()

    def test_policy_navigation_and_packaged_assets(self):
        for path in ("/terms", "/privacy", "/terms.html", "/privacy.html", "/index.html"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 200)
        self.assertIn("text/css", self.client.get("/assets/app.css").headers["content-type"])
        self.assertIn("text/javascript", self.client.get("/assets/app.js").headers["content-type"])
        self.assertEqual(self.client.get("/assets/desktop.py").status_code, 404)

    def test_clear_failure_still_closes(self):
        manager = DiscordConnection()
        rpc = Mock()
        manager.rpc = rpc
        rpc.clear.side_effect = ConnectionError
        with self.assertRaises(ConnectionError):
            manager.stop()
        rpc.close.assert_called_once()
        self.assertIsNone(manager.rpc)


class HandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unresponsive_discord_handshake_has_a_deadline(self):
        from custompresence.api import Presence
        presence = Presence.__new__(Presence)
        presence.connection_timeout = 0.01
        async def stalled(client):
            await asyncio.Event().wait()
        with patch("custompresence.api.DiscordPresence.handshake", stalled):
            with self.assertRaises(TimeoutError):
                await presence.handshake()

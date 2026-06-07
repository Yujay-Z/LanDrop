import http.client
import io
import json
import queue
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from landrop_cli import build_parser, send as cli_send
from landrop_core import (
    Peer,
    Receiver,
    new_app_state,
    ping_peer,
    safe_extract_zip,
    sanitize_filename,
    discover_peers,
    send_file,
    send_path,
    unique_path,
)
from landrop_web import LanDropWebApp


def request_json(port, method, path, payload=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    data = response.read().decode("utf-8")
    connection.close()
    parsed = json.loads(data) if data else {}
    if response.status >= 400:
        raise RuntimeError(parsed.get("error", data))
    return parsed


class FileNameTests(unittest.TestCase):
    def test_sanitize_removes_path_and_windows_reserved_characters(self):
        self.assertEqual(sanitize_filename("../bad:name?.txt"), "bad_name_.txt")

    def test_sanitize_falls_back_when_name_is_empty(self):
        self.assertEqual(sanitize_filename("..."), "received-file")

    def test_unique_path_adds_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = Path(tmp) / "report.txt"
            first.write_text("existing", encoding="utf-8")
            self.assertEqual(unique_path(tmp, "report.txt").name, "report (1).txt")


class TransferTests(unittest.TestCase):
    def test_send_file_to_local_receiver(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as receive_dir:
            source = Path(source_dir) / "hello.txt"
            source.write_text("hello from mac to windows", encoding="utf-8")
            state = new_app_state(name="Test Receiver", code="123456", receive_dir=receive_dir, events=queue.Queue())
            receiver = Receiver(state, host="127.0.0.1", enable_discovery=False)
            receiver.start()
            try:
                peer = Peer(name="local", host="127.0.0.1", port=receiver.port)
                send_file(peer, source, "123456")
                received = Path(receive_dir) / "hello.txt"
                self.assertEqual(received.read_text(encoding="utf-8"), "hello from mac to windows")
            finally:
                receiver.stop()

    def test_ping_peer_reads_receiver_identity(self):
        with tempfile.TemporaryDirectory() as receive_dir:
            state = new_app_state(name="Ping Receiver", code="123456", receive_dir=receive_dir, events=queue.Queue())
            receiver = Receiver(state, host="127.0.0.1", enable_discovery=False)
            receiver.start()
            try:
                peer = ping_peer(Peer(name="manual", host="127.0.0.1", port=receiver.port))
                self.assertEqual(peer.name, "Ping Receiver")
                self.assertEqual(peer.host, "127.0.0.1")
                self.assertEqual(peer.port, receiver.port)
            finally:
                receiver.stop()

    def test_send_file_rejects_wrong_code(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as receive_dir:
            source = Path(source_dir) / "secret.txt"
            source.write_text("not today", encoding="utf-8")
            state = new_app_state(name="Test Receiver", code="123456", receive_dir=receive_dir, events=queue.Queue())
            receiver = Receiver(state, host="127.0.0.1", enable_discovery=False)
            receiver.start()
            try:
                peer = Peer(name="local", host="127.0.0.1", port=receiver.port)
                with self.assertRaisesRegex(RuntimeError, "Invalid receive code"):
                    send_file(peer, source, "000000")
                self.assertFalse((Path(receive_dir) / "secret.txt").exists())
            finally:
                receiver.stop()

    def test_send_folder_to_local_receiver(self):
        with tempfile.TemporaryDirectory() as source_root, tempfile.TemporaryDirectory() as receive_dir:
            source = Path(source_root) / "Project"
            nested = source / "docs"
            nested.mkdir(parents=True)
            (source / "README.txt").write_text("root file", encoding="utf-8")
            (nested / "notes.txt").write_text("nested file", encoding="utf-8")
            state = new_app_state(name="Test Receiver", code="123456", receive_dir=receive_dir, events=queue.Queue())
            receiver = Receiver(state, host="127.0.0.1", enable_discovery=False)
            receiver.start()
            try:
                peer = Peer(name="local", host="127.0.0.1", port=receiver.port)
                send_path(peer, source, "123456")
                received = Path(receive_dir) / "Project"
                self.assertEqual((received / "README.txt").read_text(encoding="utf-8"), "root file")
                self.assertEqual((received / "docs" / "notes.txt").read_text(encoding="utf-8"), "nested file")
            finally:
                receiver.stop()


class ZipSafetyTests(unittest.TestCase):
    def test_safe_extract_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../escape.txt", "bad")
            with self.assertRaisesRegex(ValueError, "Unsafe path"):
                safe_extract_zip(archive, Path(tmp) / "out")
            self.assertFalse((Path(tmp) / "escape.txt").exists())


class DiscoveryTests(unittest.TestCase):
    def test_discover_returns_empty_when_broadcast_is_unavailable(self):
        with patch("landrop_core.socket.socket") as socket_factory:
            sock = socket_factory.return_value.__enter__.return_value
            sock.sendto.side_effect = OSError("No route to host")
            self.assertEqual(discover_peers(timeout=0.01), [])


class CliTests(unittest.TestCase):
    def test_cli_send_accepts_files_and_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = Path(tmp) / "one.txt"
            folder_path = Path(tmp) / "folder"
            file_path.write_text("one", encoding="utf-8")
            folder_path.mkdir()
            (folder_path / "two.txt").write_text("two", encoding="utf-8")
            args = build_parser().parse_args(
                [
                    "send",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "9999",
                    "--code",
                    "123456",
                    str(file_path),
                    str(folder_path),
                ]
            )
            with patch("landrop_cli.send_path") as mocked, redirect_stdout(io.StringIO()):
                self.assertEqual(cli_send(args), 0)
            self.assertEqual(mocked.call_count, 2)


class WebApiTests(unittest.TestCase):
    def test_web_ui_includes_manual_peer_controls(self):
        from landrop_web import INDEX_HTML

        self.assertIn('id="manualHost"', INDEX_HTML)
        self.assertIn('id="manualPort"', INDEX_HTML)
        self.assertIn('id="testManualPeer"', INDEX_HTML)

    def test_web_status_and_discovery_interfaces(self):
        app = LanDropWebApp(open_browser=False, receiver_host="127.0.0.1", enable_discovery=False)
        app.start()
        try:
            status = request_json(app.port, "GET", "/api/status")
            self.assertEqual(status["app"], "LanDrop")
            self.assertEqual(len(status["code"]), 6)
            with patch("landrop_web.discover_peers", return_value=[Peer("Desk", "192.168.1.5", 12345)]):
                peers = request_json(app.port, "GET", "/api/peers?timeout=0.01")
            self.assertEqual(peers["peers"][0]["name"], "Desk")
        finally:
            app.stop()

    def test_web_send_paths_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "web.txt"
            source.write_text("from web", encoding="utf-8")
            app = LanDropWebApp(open_browser=False, receiver_host="127.0.0.1", enable_discovery=False)
            app.start()
            try:
                payload = {
                    "peer": {"name": "Desk", "host": "192.168.1.5", "port": 12345},
                    "code": "123456",
                    "paths": [str(source)],
                }
                with patch("landrop_web.send_path") as mocked:
                    response = request_json(app.port, "POST", "/api/send-paths", payload)
                self.assertTrue(response["ok"])
                mocked.assert_called_once()
            finally:
                app.stop()

    def test_web_ping_peer_interface(self):
        with tempfile.TemporaryDirectory() as receive_dir:
            state = new_app_state(name="Manual Desk", code="123456", receive_dir=receive_dir, events=queue.Queue())
            receiver = Receiver(state, host="127.0.0.1", enable_discovery=False)
            app = LanDropWebApp(open_browser=False, receiver_host="127.0.0.1", enable_discovery=False)
            receiver.start()
            app.start()
            try:
                payload = {"host": "127.0.0.1", "port": receiver.port}
                response = request_json(app.port, "POST", "/api/ping-peer", payload)
                self.assertTrue(response["ok"])
                self.assertEqual(response["peer"]["name"], "Manual Desk")
                self.assertEqual(response["peer"]["port"], receiver.port)
            finally:
                app.stop()
                receiver.stop()


if __name__ == "__main__":
    unittest.main()

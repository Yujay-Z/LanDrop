import http.client
import json
import os
import platform
import queue
import random
import re
import shutil
import socket
import stat
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, quote, unquote, urlparse


APP_NAME = "LanDrop"
DISCOVERY_PORT = 45678
DISCOVERY_MESSAGE = b"LANDROP_DISCOVER_V1"
CHUNK_SIZE = 1024 * 256
TRANSFER_FILE = "file"
TRANSFER_FOLDER = "folder"


def sanitize_filename(name):
    name = Path(name).name.strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = name.rstrip(" .")
    return name or "received-file"


def unique_path(folder, filename):
    folder = Path(folder)
    clean_name = sanitize_filename(filename)
    candidate = folder / clean_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = folder / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def safe_relative_parts(name):
    normalized = str(name).replace("\\", "/")
    path = PurePosixPath(normalized)
    parts = path.parts
    if not parts or path.is_absolute():
        raise ValueError(f"Unsafe path: {name}")
    if parts[0].endswith(":"):
        raise ValueError(f"Unsafe path: {name}")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError(f"Unsafe path: {name}")
    return parts


def safe_child_path(root, relative_name):
    root = Path(root).resolve()
    target = root.joinpath(*safe_relative_parts(relative_name)).resolve()
    if os.path.commonpath([str(root), str(target)]) != str(root):
        raise ValueError(f"Unsafe path: {relative_name}")
    return target


def zip_folder(folder, archive_path):
    folder = Path(folder)
    archive_path = Path(archive_path)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        wrote_any = False
        for current, dirnames, filenames in os.walk(folder):
            current_path = Path(current)
            relative_dir = current_path.relative_to(folder)
            if relative_dir != Path(".") and not dirnames and not filenames:
                archive.write(current_path, relative_dir.as_posix() + "/")
                wrote_any = True
            for filename in filenames:
                file_path = current_path / filename
                archive.write(file_path, file_path.relative_to(folder).as_posix())
                wrote_any = True
        if not wrote_any:
            archive.writestr(".landrop-empty-folder", "")


def safe_extract_zip(archive_path, target_dir):
    archive_path = Path(archive_path)
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    with zipfile.ZipFile(archive_path, "r") as archive:
        for info in archive.infolist():
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Unsafe symlink in archive: {info.filename}")
            if info.filename == ".landrop-empty-folder":
                continue
            target = safe_child_path(target_dir, info.filename)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            extracted += 1
    return extracted


def _write_request_body(source, output, total_size):
    written = 0
    while written < total_size:
        chunk = source.read(min(CHUNK_SIZE, total_size - written))
        if not chunk:
            raise ConnectionError("Connection closed before upload completed")
        output.write(chunk)
        written += len(chunk)
    return written


def device_name():
    name = platform.node().strip()
    return name or f"{platform.system()} Device"


def generate_code():
    return f"{random.randint(0, 999999):06d}"


@dataclass
class Peer:
    name: str
    host: str
    port: int

    @property
    def label(self):
        return f"{self.name}  ({self.host}:{self.port})"


class UploadHandler(BaseHTTPRequestHandler):
    server_version = "LanDropHTTP/1.0"

    def do_GET(self):
        if urlparse(self.path).path != "/ping":
            self.send_error(404)
            return
        payload = {
            "app": APP_NAME,
            "name": self.server.app_state["name"],
            "port": self.server.server_port,
        }
        self._send_json(200, payload)

    def do_PUT(self):
        if urlparse(self.path).path != "/upload":
            self.send_error(404)
            return

        expected_code = self.server.app_state["code"]
        provided_code = self.headers.get("X-LanDrop-Code", "")
        if provided_code != expected_code:
            self._send_json(403, {"ok": False, "error": "Invalid receive code"})
            return

        length_header = self.headers.get("Content-Length")
        if not length_header:
            self._send_json(411, {"ok": False, "error": "Missing Content-Length"})
            return

        try:
            total_size = int(length_header)
        except ValueError:
            self._send_json(400, {"ok": False, "error": "Invalid Content-Length"})
            return

        transfer_type = self.headers.get("X-LanDrop-Type", TRANSFER_FILE).lower()
        if transfer_type not in (TRANSFER_FILE, TRANSFER_FOLDER):
            self._send_json(400, {"ok": False, "error": "Invalid transfer type"})
            return

        query = parse_qs(urlparse(self.path).query)
        filename = unquote(query.get("filename", ["received-file"])[0])
        display_name = unquote(self.headers.get("X-LanDrop-Name", "")) or filename
        receive_dir = Path(self.server.app_state["receive_dir"])
        receive_dir.mkdir(parents=True, exist_ok=True)

        written = 0
        target = None
        temp_path = None
        try:
            if transfer_type == TRANSFER_FOLDER:
                target = unique_path(receive_dir, display_name)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", dir=receive_dir) as temp_file:
                    temp_path = Path(temp_file.name)
                    written = _write_request_body(self.rfile, temp_file, total_size)
                safe_extract_zip(temp_path, target)
                temp_path.unlink(missing_ok=True)
                temp_path = None
            else:
                target = unique_path(receive_dir, display_name)
                with target.open("wb") as out_file:
                    written = _write_request_body(self.rfile, out_file, total_size)

            noun = "文件夹" if transfer_type == TRANSFER_FOLDER else "文件"
            self.server.app_state["events"].put(
                ("received", f"收到{noun}：{target.name} ({written} bytes)")
            )
            self._send_json(
                200,
                {"ok": True, "name": target.name, "type": transfer_type, "bytes": written},
            )
        except Exception as exc:
            if temp_path:
                temp_path.unlink(missing_ok=True)
            if transfer_type == TRANSFER_FOLDER and target and target.exists():
                shutil.rmtree(target, ignore_errors=True)
            elif target and target.exists():
                target.unlink(missing_ok=True)
            self.server.app_state["events"].put(("error", f"接收失败：{exc}"))
            self._send_json(500, {"ok": False, "error": str(exc)})

    def log_message(self, format, *args):
        return

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class Receiver:
    def __init__(self, app_state, host="", enable_discovery=True):
        self.app_state = app_state
        self.host = host
        self.enable_discovery = enable_discovery
        self.httpd = None
        self.thread = None
        self.discovery_thread = None
        self.stop_event = threading.Event()

    @property
    def port(self):
        if not self.httpd:
            return None
        return self.httpd.server_port

    def start(self):
        self.httpd = ThreadingHTTPServer((self.host, 0), UploadHandler)
        self.httpd.app_state = self.app_state
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        if self.enable_discovery:
            self.discovery_thread = threading.Thread(target=self._serve_discovery, daemon=True)
            self.discovery_thread.start()

    def stop(self):
        self.stop_event.set()
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    def _serve_discovery(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("", DISCOVERY_PORT))
            sock.settimeout(0.5)
            while not self.stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if data != DISCOVERY_MESSAGE:
                    continue
                payload = json.dumps(
                    {
                        "app": APP_NAME,
                        "name": self.app_state["name"],
                        "port": self.port,
                    }
                ).encode("utf-8")
                sock.sendto(payload, addr)


def new_app_state(name=None, code=None, receive_dir=None, events=None):
    return {
        "name": name or device_name(),
        "code": code or generate_code(),
        "receive_dir": str(receive_dir or Path.home() / "Downloads" / "LanDrop"),
        "events": events or queue.Queue(),
    }


def discover_peers(timeout=1.2):
    peers = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.2)
        try:
            sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", DISCOVERY_PORT))
        except OSError:
            return []
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if payload.get("app") != APP_NAME:
                continue
            port = payload.get("port")
            name = payload.get("name") or addr[0]
            if isinstance(port, int):
                peers[(addr[0], port)] = Peer(name=name, host=addr[0], port=port)
    return list(peers.values())


def ping_peer(peer, timeout=3):
    connection = http.client.HTTPConnection(peer.host, peer.port, timeout=timeout)
    try:
        connection.request("GET", "/ping")
        response = connection.getresponse()
        body = response.read().decode("utf-8", errors="replace")
    finally:
        connection.close()
    if response.status >= 400:
        raise RuntimeError(f"HTTP {response.status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid ping response") from exc
    if payload.get("app") != APP_NAME:
        raise RuntimeError("Not a LanDrop peer")
    name = payload.get("name") or peer.name
    port = payload.get("port") if isinstance(payload.get("port"), int) else peer.port
    return Peer(name=name, host=peer.host, port=port)


def _send_upload(peer, payload_path, code, transfer_type, display_name, progress_callback=None):
    payload_path = Path(payload_path)
    total_size = payload_path.stat().st_size
    connection = http.client.HTTPConnection(peer.host, peer.port, timeout=30)
    url = f"/upload?filename={quote(payload_path.name, safe='')}"
    headers = {
        "Content-Length": str(total_size),
        "X-LanDrop-Code": code,
        "X-LanDrop-Type": transfer_type,
        "X-LanDrop-Name": quote(display_name, safe=""),
        "Content-Type": "application/octet-stream",
    }

    connection.putrequest("PUT", url)
    for key, value in headers.items():
        connection.putheader(key, value)
    connection.endheaders()

    sent = 0
    with payload_path.open("rb") as in_file:
        while True:
            chunk = in_file.read(CHUNK_SIZE)
            if not chunk:
                break
            connection.send(chunk)
            sent += len(chunk)
            if progress_callback:
                progress_callback(sent, total_size)

    response = connection.getresponse()
    body = response.read().decode("utf-8", errors="replace")
    connection.close()
    if response.status >= 400:
        try:
            payload = json.loads(body)
            message = payload.get("error", body)
        except json.JSONDecodeError:
            message = body
        raise RuntimeError(message or f"HTTP {response.status}")
    return body


def send_file(peer, file_path, code, progress_callback=None, display_name=None):
    file_path = Path(file_path)
    return _send_upload(
        peer,
        file_path,
        code,
        TRANSFER_FILE,
        display_name or file_path.name,
        progress_callback,
    )


def send_path(peer, path, code, progress_callback=None, display_name=None):
    path = Path(path)
    if path.is_file():
        return send_file(peer, path, code, progress_callback, display_name=display_name)
    if not path.is_dir():
        raise FileNotFoundError(f"Not a file or folder: {path}")

    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / f"{sanitize_filename(display_name or path.name)}.zip"
        zip_folder(path, archive_path)
        return _send_upload(
            peer,
            archive_path,
            code,
            TRANSFER_FOLDER,
            display_name or path.name,
            progress_callback,
        )

import argparse
import json
import tempfile
import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from landrop_core import (
    APP_NAME,
    CHUNK_SIZE,
    Peer,
    Receiver,
    discover_peers,
    generate_code,
    new_app_state,
    ping_peer,
    safe_child_path,
    sanitize_filename,
    send_file,
    send_path,
)


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>LanDrop</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --line: #d7dce2;
      --text: #17202a;
      --muted: #667085;
      --accent: #0f766e;
      --accent-strong: #115e59;
      --danger: #b42318;
      --focus: #2563eb;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 15px;
      letter-spacing: 0;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 {
      margin: 0;
      font-size: 22px;
      line-height: 1.2;
      font-weight: 700;
    }
    main {
      width: min(1120px, 100%);
      margin: 0 auto;
      padding: 22px;
      display: grid;
      grid-template-columns: minmax(280px, 360px) 1fr;
      gap: 18px;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }
    h2 {
      margin: 0 0 14px;
      font-size: 16px;
      font-weight: 700;
    }
    label {
      display: block;
      margin: 12px 0 6px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 600;
    }
    input, select, button {
      width: 100%;
      min-height: 38px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--text);
      font: inherit;
    }
    input, select {
      padding: 7px 9px;
    }
    button {
      padding: 8px 11px;
      cursor: pointer;
      font-weight: 700;
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    button.primary:hover { background: var(--accent-strong); }
    button:focus, input:focus, select:focus {
      outline: 2px solid var(--focus);
      outline-offset: 1px;
    }
    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      align-items: end;
    }
    .code {
      font-size: 30px;
      font-weight: 800;
      line-height: 1;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #f9fafb;
    }
    .meta {
      color: var(--muted);
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .stack { display: grid; gap: 12px; }
    .actions { display: flex; gap: 10px; }
    .actions button { width: auto; flex: 1; }
    .log {
      height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #0f172a;
      color: #e5e7eb;
      padding: 12px;
      font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
      font-size: 13px;
      line-height: 1.5;
      white-space: pre-wrap;
    }
    .error { color: var(--danger); }
    @media (max-width: 760px) {
      main { grid-template-columns: 1fr; padding: 14px; }
      header { padding: 16px; align-items: flex-start; flex-direction: column; }
      .row { grid-template-columns: 1fr; }
      .actions { flex-direction: column; }
      .actions button { width: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <h1>LanDrop</h1>
    <div id="headerStatus" class="meta">启动中</div>
  </header>
  <main>
    <section class="stack">
      <h2>接收</h2>
      <div class="code" id="receiveCode">------</div>
      <div class="meta" id="receiveMeta"></div>
      <button id="rotateCode">换一个接收码</button>
    </section>
    <section class="stack">
      <h2>发送</h2>
      <div class="row">
        <div>
          <label for="peerSelect">设备</label>
          <select id="peerSelect"></select>
        </div>
        <button id="refreshPeers">刷新设备</button>
      </div>
      <div class="row">
        <div>
          <label for="manualHost">手动 IP</label>
          <input id="manualHost" autocomplete="off" placeholder="192.168.1.20">
        </div>
        <div>
          <label for="manualPort">LAN 端口</label>
          <input id="manualPort" inputmode="numeric" autocomplete="off" placeholder="54321">
        </div>
      </div>
      <button id="testManualPeer">测试连接</button>
      <label for="sendCode">接收码</label>
      <input id="sendCode" inputmode="numeric" maxlength="6" placeholder="000000">
      <div class="row">
        <div>
          <label for="fileInput">文件</label>
          <input id="fileInput" type="file" multiple>
        </div>
        <button class="primary" id="sendFiles">发送文件</button>
      </div>
      <div class="row">
        <div>
          <label for="folderInput">文件夹</label>
          <input id="folderInput" type="file" webkitdirectory directory multiple>
        </div>
        <button class="primary" id="sendFolder">发送文件夹</button>
      </div>
      <div id="sendStatus" class="meta"></div>
    </section>
    <section style="grid-column: 1 / -1;">
      <h2>传输记录</h2>
      <div class="log" id="log"></div>
    </section>
  </main>
  <script>
    const state = { peers: [] };

    async function request(path, options) {
      const response = await fetch(path, options);
      const text = await response.text();
      const data = text ? JSON.parse(text) : {};
      if (!response.ok) throw new Error(data.error || text || response.statusText);
      return data;
    }

    function manualPeer() {
      const host = document.getElementById("manualHost").value.trim();
      const portText = document.getElementById("manualPort").value.trim();
      if (!host && !portText) return null;
      if (!host) throw new Error("请输入接收端 IP");
      const port = Number(portText);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        throw new Error("请输入有效端口");
      }
      return { name: host, host, port };
    }

    function selectedPeer() {
      const manual = manualPeer();
      if (manual) return manual;
      const index = document.getElementById("peerSelect").selectedIndex;
      return state.peers[index] || null;
    }

    function renderPeers() {
      const select = document.getElementById("peerSelect");
      select.innerHTML = "";
      for (const peer of state.peers) {
        const option = document.createElement("option");
        option.textContent = `${peer.name} (${peer.host}:${peer.port})`;
        select.appendChild(option);
      }
    }

    async function refreshStatus() {
      const status = await request("/api/status");
      document.getElementById("receiveCode").textContent = status.code;
      document.getElementById("headerStatus").textContent = status.name;
      document.getElementById("receiveMeta").textContent =
        `${status.receive_dir} · LAN ${status.receiver_port}`;
    }

    async function refreshPeers() {
      document.getElementById("sendStatus").textContent = "正在刷新设备";
      const data = await request("/api/peers");
      state.peers = data.peers;
      renderPeers();
      document.getElementById("sendStatus").textContent =
        state.peers.length ? `发现 ${state.peers.length} 台设备` : "没有发现设备";
    }

    async function refreshLogs() {
      const data = await request("/api/logs");
      const lines = data.logs.map(item => `${item.time}  ${item.message}`);
      const log = document.getElementById("log");
      log.textContent = lines.join("\n");
      log.scrollTop = log.scrollHeight;
    }

    async function rotateCode() {
      const status = await request("/api/code", { method: "POST" });
      document.getElementById("receiveCode").textContent = status.code;
      await refreshLogs();
    }

    async function testManualPeer() {
      const peer = manualPeer();
      if (!peer) throw new Error("请输入接收端 IP 和端口");
      const data = await request("/api/ping-peer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(peer)
      });
      const found = data.peer;
      state.peers = [found, ...state.peers.filter(item => item.host !== found.host || item.port !== found.port)];
      renderPeers();
      document.getElementById("peerSelect").selectedIndex = 0;
      document.getElementById("manualHost").value = "";
      document.getElementById("manualPort").value = "";
      document.getElementById("sendStatus").textContent = `连接正常：${found.name}`;
      await refreshLogs();
    }

    async function sendFiles() {
      const input = document.getElementById("fileInput");
      await uploadFiles([...input.files], "file");
      input.value = "";
    }

    async function sendFolder() {
      const input = document.getElementById("folderInput");
      await uploadFiles([...input.files], "folder");
      input.value = "";
    }

    async function uploadFiles(files, type) {
      const peer = selectedPeer();
      const code = document.getElementById("sendCode").value.trim();
      if (!peer) throw new Error("请先选择设备");
      if (!/^\d{6}$/.test(code)) throw new Error("请输入 6 位接收码");
      if (!files.length) throw new Error(type === "folder" ? "请选择文件夹" : "请选择文件");

      const batch = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
      const rootName = type === "folder"
        ? ((files[0].webkitRelativePath || files[0].name).split("/")[0] || "folder")
        : "";

      for (let index = 0; index < files.length; index += 1) {
        const file = files[index];
        const params = new URLSearchParams({
          host: peer.host,
          port: String(peer.port),
          code,
          type,
          name: type === "folder" ? rootName : file.name,
          batch,
          total: String(files.length)
        });
        if (type === "folder") {
          const fullPath = file.webkitRelativePath || file.name;
          const parts = fullPath.split("/");
          params.set("relative_path", parts.length > 1 ? parts.slice(1).join("/") : file.name);
        }
        document.getElementById("sendStatus").textContent =
          `正在发送 ${index + 1}/${files.length}: ${file.name}`;
        await request(`/api/upload?${params}`, { method: "POST", body: file });
      }
      document.getElementById("sendStatus").textContent = "发送完成";
      await refreshLogs();
    }

    function bind(id, fn) {
      document.getElementById(id).addEventListener("click", async () => {
        try { await fn(); }
        catch (error) {
          document.getElementById("sendStatus").innerHTML =
            `<span class="error">${error.message}</span>`;
        }
      });
    }

    bind("rotateCode", rotateCode);
    bind("refreshPeers", refreshPeers);
    bind("testManualPeer", testManualPeer);
    bind("sendFiles", sendFiles);
    bind("sendFolder", sendFolder);
    refreshStatus();
    refreshPeers().catch(() => {});
    refreshLogs();
    setInterval(refreshStatus, 3000);
    setInterval(refreshLogs, 2000);
  </script>
</body>
</html>
"""


@dataclass
class FolderBatch:
    tempdir: tempfile.TemporaryDirectory
    folder: Path
    peer: Peer
    code: str
    name: str
    total: int
    received: int = 0


class LanDropWebApp:
    def __init__(
        self,
        receive_dir=None,
        name=None,
        control_host="127.0.0.1",
        control_port=0,
        open_browser=True,
        receiver_host="",
        enable_discovery=True,
    ):
        self.events = tempfile_queue()
        self.logs = []
        self.log_lock = threading.Lock()
        self.batches = {}
        self.batch_lock = threading.Lock()
        self.control_host = control_host
        self.control_port = control_port
        self.open_browser = open_browser
        self.app_state = new_app_state(name=name, receive_dir=receive_dir, events=self.events)
        self.receiver = Receiver(self.app_state, host=receiver_host, enable_discovery=enable_discovery)
        self.httpd = None
        self.thread = None

    @property
    def port(self):
        if not self.httpd:
            return None
        return self.httpd.server_port

    @property
    def url(self):
        return f"http://{self.control_host}:{self.port}/"

    def start(self):
        self.receiver.start()
        self.httpd = ThreadingHTTPServer((self.control_host, self.control_port), WebHandler)
        self.httpd.web_app = self
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.add_log("info", f"Web UI 已启动：{self.url}")
        self.add_log("info", f"接收服务端口：{self.receiver.port}")
        if self.open_browser:
            threading.Timer(0.4, lambda: webbrowser.open(self.url)).start()

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.receiver.stop()
        with self.batch_lock:
            batches = list(self.batches.values())
            self.batches.clear()
        for batch in batches:
            batch.tempdir.cleanup()

    def add_log(self, level, message):
        with self.log_lock:
            self.logs.append({"time": time.strftime("%H:%M:%S"), "level": level, "message": message})
            self.logs = self.logs[-200:]

    def drain_events(self):
        while True:
            try:
                level, message = self.events.get_nowait()
            except Exception:
                break
            self.add_log(level, message)

    def rotate_code(self):
        self.app_state["code"] = generate_code()
        self.add_log("info", f"新的接收码：{self.app_state['code']}")
        return self.app_state["code"]

    def get_or_create_batch(self, batch_id, total, peer, code, name):
        with self.batch_lock:
            batch = self.batches.get(batch_id)
            if batch:
                return batch
            tempdir = tempfile.TemporaryDirectory()
            folder = Path(tempdir.name) / sanitize_filename(name)
            folder.mkdir(parents=True, exist_ok=True)
            batch = FolderBatch(tempdir, folder, peer, code, name, total)
            self.batches[batch_id] = batch
            return batch

    def pop_batch(self, batch_id):
        with self.batch_lock:
            return self.batches.pop(batch_id, None)


def tempfile_queue():
    import queue

    return queue.Queue()


class WebHandler(BaseHTTPRequestHandler):
    server_version = "LanDropWeb/1.0"

    @property
    def app(self):
        return self.server.web_app

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self._send_html(INDEX_HTML)
        elif path == "/api/status":
            self.app.drain_events()
            self._send_json(
                200,
                {
                    "app": APP_NAME,
                    "name": self.app.app_state["name"],
                    "code": self.app.app_state["code"],
                    "receive_dir": self.app.app_state["receive_dir"],
                    "receiver_port": self.app.receiver.port,
                    "control_port": self.app.port,
                },
            )
        elif path == "/api/logs":
            self.app.drain_events()
            with self.app.log_lock:
                logs = list(self.app.logs)
            self._send_json(200, {"logs": logs})
        elif path == "/api/peers":
            query = parse_qs(urlparse(self.path).query)
            timeout = float(query.get("timeout", ["1.2"])[0])
            peers = discover_peers(timeout=timeout)
            self._send_json(
                200,
                {"peers": [{"name": peer.name, "host": peer.host, "port": peer.port} for peer in peers]},
            )
        else:
            self._send_json(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/code":
                code = self.app.rotate_code()
                self._send_json(200, {"ok": True, "code": code})
            elif path == "/api/ping-peer":
                self._handle_ping_peer()
            elif path == "/api/send-paths":
                self._handle_send_paths()
            elif path == "/api/upload":
                self._handle_upload()
            else:
                self._send_json(404, {"ok": False, "error": "Not found"})
        except Exception as exc:
            self.app.add_log("error", f"操作失败：{exc}")
            self._send_json(500, {"ok": False, "error": str(exc)})

    def _handle_ping_peer(self):
        payload = self._read_json()
        peer = Peer(
            name=payload.get("name") or payload["host"],
            host=payload["host"],
            port=int(payload["port"]),
        )
        found = ping_peer(peer)
        self.app.add_log("info", f"连接正常：{found.name} ({found.host}:{found.port})")
        self._send_json(
            200,
            {
                "ok": True,
                "peer": {"name": found.name, "host": found.host, "port": found.port},
            },
        )

    def _handle_send_paths(self):
        payload = self._read_json()
        peer_data = payload.get("peer", payload)
        peer = Peer(
            name=peer_data.get("name") or peer_data["host"],
            host=peer_data["host"],
            port=int(peer_data["port"]),
        )
        code = payload["code"]
        sent = []
        for path_name in payload.get("paths", []):
            path = Path(path_name)
            send_path(peer, path, code)
            sent.append(path.name)
            self.app.add_log("sent", f"发送完成：{path.name}")
        self._send_json(200, {"ok": True, "sent": sent})

    def _handle_upload(self):
        query = parse_qs(urlparse(self.path).query)
        transfer_type = self._query_value(query, "type")
        name = self._query_value(query, "name")
        peer = Peer(
            name=self._query_value(query, "host"),
            host=self._query_value(query, "host"),
            port=int(self._query_value(query, "port")),
        )
        code = self._query_value(query, "code")

        if transfer_type == "file":
            with tempfile.TemporaryDirectory() as tmp:
                temp_path = Path(tmp) / sanitize_filename(name)
                self._write_body_to(temp_path)
                send_file(peer, temp_path, code, display_name=name)
            self.app.add_log("sent", f"发送完成：{name}")
            self._send_json(200, {"ok": True, "sent": True, "name": name})
            return

        if transfer_type != "folder":
            raise ValueError("Invalid upload type")

        batch_id = self._query_value(query, "batch")
        total = int(self._query_value(query, "total"))
        relative_path = self._query_value(query, "relative_path")
        batch = self.app.get_or_create_batch(batch_id, total, peer, code, name)
        target = safe_child_path(batch.folder, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._write_body_to(target)
        batch.received += 1

        if batch.received >= batch.total:
            finished = self.app.pop_batch(batch_id)
            try:
                send_path(finished.peer, finished.folder, finished.code, display_name=finished.name)
                self.app.add_log("sent", f"发送完成：{finished.name}")
            finally:
                finished.tempdir.cleanup()
            self._send_json(200, {"ok": True, "sent": True, "name": finished.name})
        else:
            self._send_json(200, {"ok": True, "sent": False, "received": batch.received, "total": batch.total})

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _write_body_to(self, target):
        length = int(self.headers.get("Content-Length", "0"))
        written = 0
        with Path(target).open("wb") as output:
            while written < length:
                chunk = self.rfile.read(min(CHUNK_SIZE, length - written))
                if not chunk:
                    raise ConnectionError("Upload closed before request body completed")
                output.write(chunk)
                written += len(chunk)

    def _query_value(self, query, key):
        values = query.get(key)
        if not values or values[0] == "":
            raise ValueError(f"Missing parameter: {key}")
        return values[0]

    def _send_html(self, html):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def build_parser():
    parser = argparse.ArgumentParser(description="LanDrop 本地 Web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Web UI 监听地址")
    parser.add_argument("--port", type=int, default=0, help="Web UI 端口；0 表示自动选择")
    parser.add_argument("--receive-dir", default=None, help="接收文件夹")
    parser.add_argument("--name", default=None, help="设备名")
    parser.add_argument("--no-browser", action="store_true", help="启动后不自动打开浏览器")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    app = LanDropWebApp(
        receive_dir=args.receive_dir,
        name=args.name,
        control_host=args.host,
        control_port=args.port,
        open_browser=not args.no_browser,
    )
    app.start()
    print(f"LanDrop Web UI: {app.url}")
    print(f"接收码: {app.app_state['code']}")
    print("按 Ctrl+C 停止")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n正在停止 LanDrop...")
    finally:
        app.stop()


if __name__ == "__main__":
    raise SystemExit(main())

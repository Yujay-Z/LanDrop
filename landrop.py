import queue
import re
import threading
import time
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError as exc:
    raise SystemExit(
        "LanDrop GUI 需要 Python 的 Tkinter 支持。\n"
        "Windows 建议使用 python.org 安装包；macOS 可安装带 Tk 的 Python，"
        "或继续使用后续 CLI/打包版本。"
    ) from exc

from landrop_core import Receiver, discover_peers, generate_code, new_app_state, send_path


class LanDropApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LanDrop")
        self.geometry("760x520")
        self.minsize(680, 460)

        self.events = queue.Queue()
        self.app_state = new_app_state(events=self.events)
        self.peers = []
        self.selected_files = []
        self.receive_dir = tk.StringVar(value=self.app_state["receive_dir"])
        self.receive_code = tk.StringVar(value=self.app_state["code"])
        self.status = tk.StringVar(value="正在启动接收服务...")
        self.peer_status = tk.StringVar(value="尚未刷新设备")
        self.send_code = tk.StringVar()

        self.receiver = Receiver(self.app_state)
        self.receiver.start()

        self._build_ui()
        self._refresh_status()
        self.after(200, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build_ui(self):
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        receive = ttk.LabelFrame(root, text="接收")
        receive.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 12))
        receive.columnconfigure(1, weight=1)

        ttk.Label(receive, text="本机名称").grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        ttk.Label(receive, text=self.app_state["name"]).grid(row=0, column=1, sticky="w", padx=10, pady=(10, 4))
        ttk.Label(receive, text="接收码").grid(row=1, column=0, sticky="w", padx=10, pady=4)
        ttk.Label(receive, textvariable=self.receive_code, font=("TkDefaultFont", 18, "bold")).grid(
            row=1, column=1, sticky="w", padx=10, pady=4
        )
        ttk.Label(receive, text="保存到").grid(row=2, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(receive, textvariable=self.receive_dir).grid(row=2, column=1, sticky="ew", padx=10, pady=4)
        ttk.Button(receive, text="选择文件夹", command=self._choose_receive_dir).grid(
            row=2, column=2, sticky="e", padx=10, pady=4
        )
        ttk.Button(receive, text="换一个接收码", command=self._rotate_code).grid(
            row=3, column=1, sticky="w", padx=10, pady=(4, 10)
        )

        send = ttk.LabelFrame(root, text="发送")
        send.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 12))
        send.columnconfigure(0, weight=1)

        ttk.Button(send, text="刷新设备", command=self._discover_async).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        self.peer_combo = ttk.Combobox(send, state="readonly")
        self.peer_combo.grid(row=1, column=0, sticky="ew", padx=10, pady=4)
        ttk.Label(send, textvariable=self.peer_status).grid(row=2, column=0, sticky="w", padx=10, pady=4)
        ttk.Entry(send, textvariable=self.send_code).grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        ttk.Button(send, text="选择文件", command=self._choose_files).grid(row=4, column=0, sticky="ew", padx=10, pady=4)
        ttk.Button(send, text="发送所选文件", command=self._send_async).grid(row=5, column=0, sticky="ew", padx=10, pady=(4, 10))

        log_frame = ttk.LabelFrame(root, text="传输记录")
        log_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        self.log.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=10)
        self.log.configure(yscrollcommand=scroll.set)

        ttk.Label(root, textvariable=self.status).grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def _refresh_status(self):
        self.app_state["receive_dir"] = self.receive_dir.get()
        self.status.set(f"接收服务已启动：端口 {self.receiver.port}，保存到 {self.receive_dir.get()}")

    def _choose_receive_dir(self):
        folder = filedialog.askdirectory(initialdir=self.receive_dir.get())
        if folder:
            self.receive_dir.set(folder)
            self._refresh_status()

    def _rotate_code(self):
        self.receive_code.set(generate_code())
        self.app_state["code"] = self.receive_code.get()
        self._log(f"新的接收码：{self.receive_code.get()}")

    def _choose_files(self):
        files = filedialog.askopenfilenames()
        if files:
            self.selected_files = list(files)
            self._log(f"已选择 {len(files)} 个文件")

    def _discover_async(self):
        self.peer_status.set("正在刷新...")
        threading.Thread(target=self._discover_worker, daemon=True).start()

    def _discover_worker(self):
        peers = discover_peers()
        self.events.put(("peers", peers))

    def _send_async(self):
        if not self.peers or self.peer_combo.current() < 0:
            messagebox.showwarning("LanDrop", "请先刷新并选择接收设备。")
            return
        if not self.selected_files:
            messagebox.showwarning("LanDrop", "请先选择要发送的文件。")
            return
        if not re.fullmatch(r"\d{6}", self.send_code.get()):
            messagebox.showwarning("LanDrop", "请输入接收端显示的 6 位接收码。")
            return
        peer = self.peers[self.peer_combo.current()]
        files = list(self.selected_files)
        code = self.send_code.get()
        threading.Thread(target=self._send_worker, args=(peer, files, code), daemon=True).start()

    def _send_worker(self, peer, files, code):
        for path in files:
            name = Path(path).name
            try:
                self.events.put(("info", f"正在发送：{name} -> {peer.name}"))
                send_path(peer, path, code)
                self.events.put(("sent", f"发送完成：{name}"))
            except Exception as exc:
                self.events.put(("error", f"发送失败：{name}，{exc}"))

    def _drain_events(self):
        while True:
            try:
                event, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if event == "peers":
                self.peers = payload
                self.peer_combo["values"] = [peer.label for peer in self.peers]
                if self.peers:
                    self.peer_combo.current(0)
                    self.peer_status.set(f"发现 {len(self.peers)} 台设备")
                else:
                    self.peer_status.set("没有发现设备")
            else:
                self._log(str(payload))
        self.after(200, self._drain_events)

    def _log(self, message):
        self.log.configure(state="normal")
        self.log.insert("end", f"{time.strftime('%H:%M:%S')}  {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _close(self):
        self.receiver.stop()
        self.destroy()


def main():
    app = LanDropApp()
    app.mainloop()


if __name__ == "__main__":
    main()

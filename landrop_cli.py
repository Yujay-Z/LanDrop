import argparse
import queue
import sys
import time
from pathlib import Path

from landrop_core import Peer, Receiver, discover_peers, generate_code, new_app_state, send_path


def path_size(path):
    path = Path(path)
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def receive(args):
    events = queue.Queue()
    code = args.code or generate_code()
    state = new_app_state(name=args.name, code=code, receive_dir=args.dir, events=events)
    receiver = Receiver(state)
    receiver.start()
    print(f"LanDrop 接收端已启动")
    print(f"设备名: {state['name']}")
    print(f"接收码: {state['code']}")
    print(f"端口: {receiver.port}")
    print(f"保存到: {state['receive_dir']}")
    print("按 Ctrl+C 停止")
    try:
        while True:
            try:
                _, message = events.get(timeout=0.5)
                print(message)
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\n正在停止接收端...")
    finally:
        receiver.stop()


def discover(args):
    peers = discover_peers(timeout=args.timeout)
    if not peers:
        print("没有发现 LanDrop 设备")
        return 1
    for peer in peers:
        print(f"{peer.name}\t{peer.host}\t{peer.port}")
    return 0


def send(args):
    peer = Peer(name=args.name or args.host, host=args.host, port=args.port)
    for path_name in args.paths:
        path = Path(path_name)
        if not path.exists():
            print(f"跳过，不存在: {path}", file=sys.stderr)
            continue
        started = time.time()
        send_path(peer, path, args.code)
        elapsed = max(time.time() - started, 0.001)
        speed = path_size(path) / elapsed / 1024 / 1024
        print(f"发送完成: {path.name} ({speed:.2f} MB/s)")
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="LanDrop 局域网文件传输")
    subparsers = parser.add_subparsers(dest="command", required=True)

    receive_parser = subparsers.add_parser("receive", help="启动接收端")
    receive_parser.add_argument("--dir", default=str(Path.home() / "Downloads" / "LanDrop"), help="接收文件夹")
    receive_parser.add_argument("--code", help="6 位接收码；不传则自动生成")
    receive_parser.add_argument("--name", help="设备名")
    receive_parser.set_defaults(func=receive)

    discover_parser = subparsers.add_parser("discover", help="发现局域网设备")
    discover_parser.add_argument("--timeout", type=float, default=1.2, help="发现超时时间，单位秒")
    discover_parser.set_defaults(func=discover)

    send_parser = subparsers.add_parser("send", help="发送文件或文件夹")
    send_parser.add_argument("--host", required=True, help="接收端 IP")
    send_parser.add_argument("--port", required=True, type=int, help="接收端端口")
    send_parser.add_argument("--code", required=True, help="接收端显示的 6 位接收码")
    send_parser.add_argument("--name", help="接收端名称")
    send_parser.add_argument("paths", nargs="+", help="要发送的文件或文件夹")
    send_parser.set_defaults(func=send)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "code", None) and not args.code.isdigit():
        parser.error("接收码只能包含数字")
    if getattr(args, "code", None) and len(args.code) != 6:
        parser.error("接收码必须是 6 位")
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())

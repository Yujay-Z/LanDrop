# LanDrop

LanDrop 是一个用于 macOS 和 Windows 11 的局域网文件传输工具。当前版本使用 Python 标准库实现传输核心，并提供本地 Web UI、CLI 备用入口和 GitHub Actions 双平台打包配置。

## 功能

- 在同一局域网内发现其他 LanDrop 设备
- 通过浏览器界面发送文件或文件夹
- 接收端使用 6 位接收码确认传输
- 文件夹发送时自动压缩传输，接收端安全解压为文件夹
- 自动保存到接收文件夹，重名时自动避让
- 防止恶意 zip 写出接收目录

## 本地 Web UI

最快方式：

macOS 双击：

```text
start_landrop_macos.command
```

Windows 11 双击：

```text
start_landrop_windows.bat
```

Windows 如果提示找不到 Python，请先安装 Python 3，再重新双击启动文件。

macOS:

```bash
python3 landrop_web.py
```

Windows 11:

```powershell
py landrop_web.py
```

启动后会打开本地页面。两台电脑都运行 LanDrop，发送端刷新设备，选择接收端，输入接收端显示的 6 位接收码，然后选择文件或文件夹发送。

如果自动发现没有列出对方电脑，可以在发送区手动输入接收端 IP 和页面显示的 LAN 端口，点击“测试连接”，再发送文件或文件夹。

如果不想自动打开浏览器：

```bash
python3 landrop_web.py --no-browser
```

## CLI 备用入口

接收端:

```bash
python3 landrop_cli.py receive
```

发现设备:

```bash
python3 landrop_cli.py discover
```

发送文件或文件夹:

```bash
python3 landrop_cli.py send --host 192.168.1.20 --port 54321 --code 123456 ./photo.zip ./MyFolder
```

## 旧 Tkinter GUI

仓库仍保留 `landrop.py`。如果你的 Python 带 Tkinter，也可以运行：

```bash
python3 landrop.py
```

当前主入口推荐使用 `landrop_web.py`，它不依赖 Tkinter。

## 网络和防火墙

两台电脑需要连接到同一个 Wi-Fi 或有线局域网。首次运行时，Windows 防火墙或 macOS 可能会询问是否允许网络访问，请允许局域网访问。

如果自动发现失败，可以在发送端页面手动输入接收端 IP 和 LAN 端口，或通过 CLI 使用接收端 IP 和端口发送。

## 测试

```bash
python3 -m py_compile landrop.py landrop_core.py landrop_cli.py landrop_web.py test_landrop.py
python3 -m unittest
```

本机端到端测试会临时监听 `127.0.0.1` 端口。

## 双平台打包

仓库包含 `.github/workflows/build.yml`。推送到 GitHub 后，CI 会在 macOS 和 Windows 上运行测试并打包：

- macOS: `LanDrop.app` 压缩包
- Windows: `LanDrop.exe`

也可以本地打包：

macOS:

```bash
bash scripts/build_macos.sh
```

Windows 11 PowerShell:

```powershell
.\scripts\build_windows.ps1
```

当前配置不包含安装器、签名、公证或自动更新。

# LanDrop

LanDrop 是一个用于 macOS 和 Windows 11 的局域网文件传输工具，无需互联网，无需注册账号。

## 功能

- 在同一局域网内自动发现其他 LanDrop 设备
- 通过浏览器界面发送文件或文件夹
- 6 位接收码确认传输，防止陌生设备乱传
- 文件夹自动压缩传输，接收端安全解压还原
- 自动保存，重名时自动避让，不覆盖已有文件

## Windows 安装使用

### 第一步：安装 Python

打开 [python.org/downloads](https://www.python.org/downloads/)，下载安装包。

安装时勾选 **Add Python to PATH**，然后点 Install Now。

### 第二步：下载 LanDrop

点击页面右上角绿色的 **Code → Download ZIP**，解压到任意文件夹。

或直接下载：[Download ZIP](https://github.com/Yujay-Z/LanDrop/archive/refs/heads/main.zip)

### 第三步：启动

双击解压后文件夹里的 `start_landrop_windows.bat`，浏览器会自动打开 LanDrop 界面。

## macOS 安装使用

双击项目文件夹里的 `start_landrop_macos.command`。

首次运行如果提示「无法验证开发者」，右键点击文件选择「打开」，在弹窗中点击「打开」即可。

或在终端运行：

```bash
python3 landrop_web.py
```

## 使用方法

两台电脑都运行 LanDrop，然后：

1. 接收端：记下页面左侧显示的 **6 位接收码**
2. 发送端：点「刷新设备」找到对方，填入接收码，选择文件或文件夹，点发送

找不到对方设备时，在「手动 IP」栏输入接收端的局域网 IP 和 LAN 端口，点「测试连接」后再发送。

## 网络和防火墙

两台电脑需连接同一个 Wi-Fi 或有线局域网。首次运行时，Windows 防火墙或 macOS 会询问是否允许网络访问，请点允许。

## CLI 备用入口

```bash
# 启动接收端
python3 landrop_cli.py receive

# 发现局域网设备
python3 landrop_cli.py discover

# 发送文件或文件夹
python3 landrop_cli.py send --host 192.168.1.20 --port 54321 --code 123456 ./photo.jpg ./MyFolder
```

## 测试

```bash
python3 -m py_compile landrop.py landrop_core.py landrop_cli.py landrop_web.py test_landrop.py
python3 -m unittest
```

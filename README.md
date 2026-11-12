# 倒计时 · DJS 附属功能库

本仓库存放 **倒计时·DJS** 主程序的附属功能：

- **ZX 插件**：安装到主程序 `plugins` 目录，为电脑端提供远程控制服务。
- **ZX 控制台（Windows）**：在电脑上管理多台已配对的电脑。
- **ZX 控制台（Android）**：一台手机同时管理多台电脑，修改课程表、发送教师通知。

这些组件不随主程序安装包安装，需要从本仓库 Releases 单独下载。远程控制要求设备与电脑在同一局域网，默认监听 `48700` 端口，并通过 `48690` 端口广播发现。

主程序仓库：**[Countdown-DJS](https://github.com/GuZhi-233/Countdown-DJS)**

---

## 功能

### 多设备管理

- 手机或电脑可同时连接多台安装了 ZX 插件的电脑。
- 主页显示全部已保存设备与连接状态，启动时自动尝试重连。
- 点开设备可查看详细信息、修改备注、编辑课程表、重连或解除配对。

### 课程表远程编辑

- 读取电脑端当前课程表方案。
- 支持新建、改名、删除方案，按星期编辑课程与活动。
- 保存后电脑端立即刷新。

### 教师通知

- 单台发送，或勾选多台群发。
- 电脑端以置顶通知窗展示，适合教室大屏。
- 通知标题、正文与显示时长可调。

### 配对与安全

- 电脑端生成 6 位配对码，需在电脑端二次确认。
- 配对成功后保存设备令牌，后续连接无需重复输入配对码。
- 所有错误提示均已中文化。

---

## 下载

| 内容 | 说明 |
| --- | --- |
| ZX 插件 | 解压后把 `zx.py` 与 `zx.json` 放入主程序 `plugins` 目录 |
| ZX 控制台（Windows） | 安装后从开始菜单或桌面启动 |
| ZX 控制台（Android） | 直接安装 APK |

下载地址：本仓库的 Releases 页面。

---

## 安装 ZX 插件

1. 打开主程序所在目录。
2. 进入 `plugins` 文件夹；不存在时手动创建。
3. 把 `zx.py` 与 `zx.json` 复制进去。
4. 打开主程序 → 设置 → 插件管理 → 启用插件系统。
5. 启用 ZX 插件。
6. 打开 ZX 设置页 → 远程 → 勾选“启用远程控制”。
7. 点击“生成配对码”，电脑名称与配对码会显示在该页。

电脑端默认监听 `48700` 端口，并通过 `48690` 端口广播发现。

---

## 配对控制台

### Windows 控制台

1. 启动 ZX 控制台。
2. 在“添加设备”页扫描局域网设备，或手动输入电脑地址与端口。
3. 输入电脑端显示的 6 位配对码。
4. 在电脑端确认配对请求。
5. 配对成功后设备出现在主页。

### Android 控制台

1. 安装 APK 并打开。
2. 点击“添加设备”，扫描或手动输入电脑地址。
3. 输入配对码并在电脑端确认。
4. 返回主页即可看到设备；下次启动会自动重连。

---

## 从源码构建

Windows 控制台：

```powershell
cd remote/windows
pip install PyQt6
python main.py
```

Android APK：

```powershell
powershell -ExecutionPolicy Bypass -File remote/android/build.ps1
```

一键构建 Windows 安装包、APK 与插件压缩包：

```powershell
powershell -ExecutionPolicy Bypass -File tools/package/build_addons.ps1
```

产物输出到 `dist/installer/`。

---

## 反馈

- Gitee Issues：https://gitee.com/guzhi233/Countdown-DJS-Addons/issues
- GitHub Issues：https://github.com/GuZhi-233/Countdown-DJS-Addons/issues
- 邮箱：guzhiawa@qq.com

---

## 许可证

[MIT License](LICENSE)

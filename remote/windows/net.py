import json

from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import (QAbstractSocket, QHostAddress, QNetworkInterface,
                             QTcpSocket, QUdpSocket)

from version import DISCOVERY_PORT


def friendly_error(text):
    value = str(text or "").strip()
    if not value:
        return "连接失败，请稍后重试"
    lower = value.lower()
    if "connection refused" in lower or "econnrefused" in lower:
        return "电脑端拒绝连接，请确认 ZX 已启用远程控制"
    if "timed out" in lower or "timeout" in lower:
        return "连接超时，请检查电脑端地址与防火墙"
    if "network is unreachable" in lower:
        return "网络不可达，请确认手机与电脑在同一局域网"
    if "no route to host" in lower:
        return "无法路由到电脑，请检查网络连接"
    if "connection reset" in lower or "broken pipe" in lower or "socket closed" in lower \
            or "connection closed" in lower:
        return "连接已被电脑端关闭"
    if "permission denied" in lower or "eacces" in lower:
        return "网络权限被拒绝"
    if "failed to connect" in lower or "unable to connect" in lower:
        return "无法连接到电脑端"
    if any("\u4e00" <= char <= "\u9fff" for char in value):
        return value
    return "连接失败，请稍后重试"


def _broadcast_addresses():
    rows = ["255.255.255.255"]
    try:
        interfaces = QNetworkInterface.allInterfaces()
    except Exception:
        return rows
    for interface in interfaces:
        try:
            if not (interface.flags() & QNetworkInterface.InterfaceFlag.IsUp):
                continue
            for entry in interface.addressEntries():
                address = entry.ip()
                mask = entry.netmask()
                if getattr(address.protocol(), "name", "") != "IPv4Protocol":
                    continue
                if address.isLoopback():
                    continue
                value = (address.toIPv4Address() & mask.toIPv4Address()) | \
                        (~mask.toIPv4Address() & 0xFFFFFFFF)
                text = str(QHostAddress(value))
                if text and text not in rows:
                    rows.append(text)
        except Exception:
            continue
    return rows


class Discovery(QObject):
    found = pyqtSignal(dict, str, int)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._socket = None
        self._seen = set()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._finish)

    def scan(self, duration=1800):
        self.stop()
        self._seen = set()
        if self._socket is None:
            self._socket = QUdpSocket(self)
            self._socket.readyRead.connect(self._read)
        if not self._socket.bind(QHostAddress(QHostAddress.SpecialAddress.AnyIPv4), 0):
            self.error.emit("无法启动局域网发现")
            self.finished.emit()
            return
        QTimer.singleShot(0, self._send_probe)
        QTimer.singleShot(450, self._send_probe)
        self._timer.start(duration)

    def _send_probe(self):
        if self._socket is None:
            return
        data = json.dumps({"zx_remote": 1, "probe": 1}).encode("utf-8")
        for address in _broadcast_addresses():
            try:
                self._socket.writeDatagram(data, QHostAddress(address), DISCOVERY_PORT)
            except Exception:
                pass

    def _read(self):
        if self._socket is None:
            return
        while self._socket.hasPendingDatagrams():
            datagram = self._socket.receiveDatagram()
            try:
                payload = json.loads(bytes(datagram.data()).decode("utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or payload.get("zx_remote") != 1:
                continue
            host = payload.get("host")
            if not isinstance(host, dict):
                continue
            try:
                port = int(payload.get("port") or 0)
            except Exception:
                continue
            if port <= 0:
                continue
            address = datagram.senderAddress().toString()
            key = "%s|%s|%d" % (host.get("id") or "", address, port)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.found.emit(host, address, port)

    def _finish(self):
        self.stop()
        self.finished.emit()

    def stop(self):
        self._timer.stop()
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass


class RemoteClient(QObject):
    paired = pyqtSignal(dict, dict, str)
    connected = pyqtSignal(dict, dict, str)
    pair_failed = pyqtSignal(str)
    disconnected = pyqtSignal(str)
    schedule_state = pyqtSignal(dict, str)
    schedule_saved = pyqtSignal(str)
    schedule_conflict = pyqtSignal(dict, str, str)
    schedule_changed = pyqtSignal(str)
    notify_result = pyqtSignal(bool, str)
    unpair_ok = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.socket = None
        self.buffer = b""
        self.host = {}
        self.state = {}
        self.rev = ""
        self.device_id = ""
        self.token = ""
        self._mode = ""
        self._pair_payload = {}
        self._hello_payload = {}
        self._closing = False
        self._authed = False
        self._pending_notify = False
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._on_timeout)

    def _create_socket(self):
        self.close()
        self._closing = False
        self._authed = False
        self.buffer = b""
        self.socket = QTcpSocket(self)
        self.socket.connected.connect(self._on_connected)
        self.socket.readyRead.connect(self._on_ready_read)
        self.socket.disconnected.connect(self._on_disconnected)
        self.socket.errorOccurred.connect(self._on_error)

    def pair(self, address, port, code, device_name, device_id, app_version):
        self._mode = "pair"
        self._pair_payload = {
            "type": "pair_request",
            "code": str(code or "").strip(),
            "device": {"id": str(device_id), "name": str(device_name), "platform": "windows"},
            "app_version": str(app_version),
        }
        self._create_socket()
        self._timeout.start(90000)
        self.socket.connectToHost(str(address), int(port))

    def hello(self, address, port, device_id, token, app_version):
        self._mode = "hello"
        self.device_id = str(device_id)
        self.token = str(token)
        self._hello_payload = {
            "type": "hello",
            "device_id": str(device_id),
            "token": str(token),
            "app_version": str(app_version),
        }
        self._create_socket()
        self._timeout.start(6000)
        self.socket.connectToHost(str(address), int(port))

    def is_connected(self):
        return self.socket is not None and self._authed and \
            self.socket.state() == QAbstractSocket.SocketState.ConnectedState

    def _on_connected(self):
        if self._mode == "pair":
            self._send(self._pair_payload)
            self._timeout.start(90000)
        elif self._mode == "hello":
            self._send(self._hello_payload)
            self._timeout.start(6000)
        else:
            self._timeout.stop()

    def _on_timeout(self):
        if self._mode == "pair":
            self.pair_failed.emit("电脑端没有响应，请稍后重试")
        elif self._mode == "hello":
            self.pair_failed.emit("连接超时，请检查电脑端地址")
        else:
            self.error.emit("请求超时")
        self.close()

    def _on_error(self, error):
        if self._closing:
            return
        message = friendly_error(self.socket.errorString() if self.socket is not None
                                 else "连接失败")
        if self._mode == "pair":
            self.pair_failed.emit(message)
        elif self._mode == "hello":
            self.pair_failed.emit(message)
        else:
            self.error.emit(message)

    def _on_disconnected(self):
        was_authed = self._authed
        self._authed = False
        if self._closing:
            return
        if self._mode == "pair" and not was_authed:
            self.pair_failed.emit("连接已断开，配对未完成")
        elif self._mode == "hello" and not was_authed:
            self.pair_failed.emit("连接已断开，请检查电脑端")
        else:
            self.disconnected.emit("与电脑端的连接已断开")

    def _send(self, payload):
        if self.socket is None or self.socket.state() != QAbstractSocket.SocketState.ConnectedState:
            return False
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.socket.write(len(data).to_bytes(4, "big") + data)
            return True
        except Exception:
            return False

    def _on_ready_read(self):
        if self.socket is None:
            return
        try:
            self.buffer += bytes(self.socket.readAll())
        except Exception:
            return
        while len(self.buffer) >= 4:
            size = int.from_bytes(self.buffer[:4], "big")
            if size <= 0 or size > 1048576:
                self.close()
                return
            if len(self.buffer) < size + 4:
                break
            raw = self.buffer[4:4 + size]
            self.buffer = self.buffer[4 + size:]
            try:
                message = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if isinstance(message, dict):
                self._dispatch(message)

    def _dispatch(self, message):
        kind = str(message.get("type") or "")
        if kind == "pair_ok":
            self._authed = True
            self._timeout.stop()
            self.host = message.get("host") or {}
            self.state = message.get("state") or {}
            self.rev = str(message.get("rev") or "")
            self.token = str(message.get("token") or "")
            self.paired.emit(self.host, self.state, self.rev)
        elif kind == "pair_reject":
            self._timeout.stop()
            self.pair_failed.emit(str(message.get("reason") or "配对失败"))
            self.close()
        elif kind == "hello_ok":
            self._authed = True
            self._timeout.stop()
            self.host = message.get("host") or {}
            self.state = message.get("state") or {}
            self.rev = str(message.get("rev") or "")
            self.connected.emit(self.host, self.state, self.rev)
        elif kind == "hello_fail":
            self._timeout.stop()
            self.pair_failed.emit(str(message.get("reason") or "配对已失效"))
            self.close()
        elif kind == "pong":
            return
        elif kind == "notify_ok":
            self._pending_notify = False
            self.notify_result.emit(True, "")
        elif kind == "schedule_state":
            self.state = message.get("state") or {}
            self.rev = str(message.get("rev") or "")
            self.schedule_state.emit(self.state, self.rev)
        elif kind == "schedule_saved":
            self.rev = str(message.get("rev") or "")
            self.schedule_saved.emit(self.rev)
        elif kind == "schedule_conflict":
            self.state = message.get("state") or self.state
            self.rev = str(message.get("rev") or self.rev)
            self.schedule_conflict.emit(message.get("state") or {}, self.rev,
                                        str(message.get("message") or "课表已被修改"))
        elif kind == "schedule_changed":
            self.schedule_changed.emit(str(message.get("rev") or ""))
        elif kind == "unpair_ok":
            self.unpair_ok.emit()
            self.close()
        elif kind == "error":
            text = str(message.get("message") or "操作失败")
            if self._pending_notify:
                self._pending_notify = False
                self.notify_result.emit(False, text)
            else:
                self.error.emit(text)

    def request_schedule(self):
        return self._send({"type": "schedule_get"})

    def save_schedule(self, state, base_rev, force=False):
        return self._send({"type": "schedule_put", "base_rev": str(base_rev or ""),
                           "state": state, "force": bool(force)})

    def send_notify(self, mode, title, body, duration):
        if not self.is_connected():
            self.notify_result.emit(False, "尚未连接电脑端")
            return False
        self._pending_notify = True
        if not self._send({"type": "notify", "mode": str(mode), "title": str(title),
                           "body": str(body), "duration": float(duration)}):
            self._pending_notify = False
            self.notify_result.emit(False, "发送失败，连接已断开")
            return False
        return True

    def unpair(self):
        if not self.is_connected():
            return False
        return self._send({"type": "unpair", "device_id": self.device_id, "token": self.token})

    def ping(self):
        return self._send({"type": "ping", "ts": 0})

    def close(self):
        self._timeout.stop()
        self._closing = True
        self._authed = False
        if self.socket is not None:
            try:
                self.socket.blockSignals(True)
                self.socket.close()
                self.socket.deleteLater()
            except Exception:
                pass
            self.socket = None
        self._closing = False

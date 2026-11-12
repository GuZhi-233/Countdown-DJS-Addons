from PyQt6.QtCore import QObject, pyqtSignal

import time

from net import RemoteClient, friendly_error
from version import DEFAULT_CONTROL_PORT, VERSION


class DeviceSession(QObject):
    changed = pyqtSignal(object)
    state_changed = pyqtSignal(object)
    saved = pyqtSignal(object, str)
    conflict = pyqtSignal(object, dict, str, str)
    notify_result = pyqtSignal(object, bool, str)
    paired = pyqtSignal(object)
    remote_changed = pyqtSignal(object, str)
    failed = pyqtSignal(object, str)

    def __init__(self, config, host, parent=None):
        super().__init__(parent)
        self.config = config
        self.host = dict(host or {})
        self.host_id = str(self.host.get("id") or "")
        self.host_name = str(self.host.get("name") or "ZX")
        self.host_version = str(self.host.get("version") or "")
        self.address = str(self.host.get("address") or "")
        self.port = int(self.host.get("port") or DEFAULT_CONTROL_PORT)
        self.token = str(self.host.get("token") or "")
        self.alias = str(self.host.get("alias") or "")
        self.state = {}
        self.rev = ""
        self.connected = False
        self.connecting = False
        self.status = "未连接"
        self.last_error = ""
        self.client = RemoteClient(self)
        self.client.paired.connect(self._on_paired)
        self.client.connected.connect(self._on_connected)
        self.client.pair_failed.connect(self._on_failed)
        self.client.disconnected.connect(self._on_disconnected)
        self.client.schedule_state.connect(self._on_state)
        self.client.schedule_saved.connect(self._on_saved)
        self.client.schedule_conflict.connect(self._on_conflict)
        self.client.schedule_changed.connect(self._on_remote)
        self.client.notify_result.connect(self._on_notify)
        self.client.unpair_ok.connect(self._on_unpair)
        self.client.error.connect(self._on_error)

    def display_name(self):
        return self.alias.strip() or self.host_name

    def key(self):
        return self.host_id or ("%s:%d" % (self.address, self.port))

    def connect_to(self):
        if not self.token:
            self.status = "未配对"
            self.connected = False
            self.changed.emit(self)
            return
        self.connecting = True
        self.connected = False
        self.status = "连接中…"
        self.last_error = ""
        self.changed.emit(self)
        self.client.hello(self.address, self.port, self.config.data.get("device_id"),
                          self.token, VERSION)

    def pair_with(self, code, address, port):
        self.address = str(address or "")
        self.port = int(port or DEFAULT_CONTROL_PORT)
        self.connecting = True
        self.connected = False
        self.status = "等待电脑端确认…"
        self.last_error = ""
        self.changed.emit(self)
        self.client.pair(self.address, self.port, code,
                         self.config.data.get("device_name"),
                         self.config.data.get("device_id"), VERSION)

    def is_connected(self):
        return self.connected and self.client.is_connected()

    def request_schedule(self):
        self.client.request_schedule()

    def save_schedule(self, state, base_rev, force=False):
        self.client.save_schedule(state, base_rev, force)

    def send_notify(self, title, body, duration):
        self.client.send_notify("quick", title, body, duration)

    def unpair(self):
        self.client.unpair()

    def close(self):
        self.client.close()

    def set_alias(self, alias):
        self.alias = str(alias or "").strip()
        self.changed.emit(self)

    def _on_paired(self, host, state, rev):
        self.host_id = str((host or {}).get("id") or self.host_id)
        self.host_name = str((host or {}).get("name") or self.host_name)
        self.host_version = str((host or {}).get("version") or self.host_version)
        self.token = self.client.token
        self.state = state or {}
        self.rev = str(rev or "")
        self.connected = True
        self.connecting = False
        self.status = "已连接"
        self.changed.emit(self)
        self.paired.emit(self)
        self.state_changed.emit(self)

    def _on_connected(self, host, state, rev):
        self.host_id = str((host or {}).get("id") or self.host_id)
        self.host_name = str((host or {}).get("name") or self.host_name)
        self.host_version = str((host or {}).get("version") or self.host_version)
        self.state = state or {}
        self.rev = str(rev or "")
        self.connected = True
        self.connecting = False
        self.status = "已连接"
        self.changed.emit(self)
        self.state_changed.emit(self)

    def _on_failed(self, message):
        self.connected = False
        self.connecting = False
        self.status = friendly_error(message)
        self.last_error = self.status
        self.changed.emit(self)
        self.failed.emit(self, self.status)

    def _on_disconnected(self, message):
        self.connected = False
        self.connecting = False
        self.status = friendly_error(message)
        self.last_error = self.status
        self.changed.emit(self)

    def _on_state(self, state, rev):
        self.state = state or {}
        self.rev = str(rev or "")
        self.state_changed.emit(self)

    def _on_saved(self, rev):
        self.rev = str(rev or "")
        self.saved.emit(self, self.rev)

    def _on_conflict(self, state, rev, message):
        self.conflict.emit(self, state or {}, str(rev or ""), message or "课表已被修改")

    def _on_remote(self, rev):
        self.remote_changed.emit(self, str(rev or ""))

    def _on_notify(self, ok, message):
        self.notify_result.emit(self, ok, message)

    def _on_unpair(self):
        self.connected = False
        self.status = "已解除配对"
        self.changed.emit(self)

    def _on_error(self, message):
        self.status = friendly_error(message)
        self.last_error = self.status
        self.changed.emit(self)


class DeviceManager(QObject):
    sessions_changed = pyqtSignal()
    session_changed = pyqtSignal(object)
    state_changed = pyqtSignal(object)
    saved = pyqtSignal(object, str)
    conflict = pyqtSignal(object, dict, str, str)
    notify_result = pyqtSignal(object, bool, str)
    paired = pyqtSignal(object)
    failed = pyqtSignal(object, str)
    remote_changed = pyqtSignal(object, str)

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.sessions = []
        self.load()

    def load(self):
        self.sessions = []
        for row in self.config.data.get("hosts") or []:
            if isinstance(row, dict):
                self._add(row)
        self.sessions_changed.emit()

    def _add(self, row):
        session = DeviceSession(self.config, row, self)
        session.changed.connect(self._on_changed)
        session.state_changed.connect(self.state_changed.emit)
        session.saved.connect(self._on_saved)
        session.conflict.connect(self.conflict.emit)
        session.notify_result.connect(self.notify_result.emit)
        session.paired.connect(self._on_paired)
        session.failed.connect(self._on_failed)
        session.remote_changed.connect(self.remote_changed.emit)
        self.sessions.append(session)
        return session

    def connect_all(self):
        for session in list(self.sessions):
            if session.token:
                session.connect_to()

    def pair_new(self, address, port, code):
        session = self._add({"name": "新设备", "address": address, "port": port})
        session.pair_with(code, address, port)
        self.sessions_changed.emit()
        return session

    def find(self, host_id):
        for session in self.sessions:
            if session.host_id == host_id:
                return session
        return None

    def remove(self, session):
        if session is None:
            return
        session.close()
        if session in self.sessions:
            self.sessions.remove(session)
        if session.host_id:
            self.config.forget_host(session.host_id)
        self.sessions_changed.emit()

    def remove_invalid(self):
        removed = 0
        for session in list(self.sessions):
            if "失效" in session.status:
                self.remove(session)
                removed += 1
        return removed

    def close_all(self):
        for session in list(self.sessions):
            session.close()

    def persist(self, session):
        if not session.host_id or not session.token:
            return
        entry = {
            "id": session.host_id,
            "name": session.host_name,
            "address": session.address,
            "port": session.port,
            "token": session.token,
            "alias": session.alias,
            "version": session.host_version,
            "last_seen": int(time.time()),
        }
        self.config.remember_host(entry)

    def _on_changed(self, session):
        self.persist(session)
        self.session_changed.emit(session)

    def _on_saved(self, session, rev):
        self.persist(session)
        self.saved.emit(session, rev)

    def _on_paired(self, session):
        self.persist(session)
        if session not in self.sessions:
            self.sessions.append(session)
        self.paired.emit(session)
        self.sessions_changed.emit()

    def _on_failed(self, session, message):
        if not session.host_id and not session.token:
            if session in self.sessions:
                self.sessions.remove(session)
            self.sessions_changed.emit()
        self.failed.emit(session, message)

import hashlib
import hmac
import json
import math
import os
import random
import re
import threading
import time
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime

from PyQt6.QtCore import (QByteArray, QDate, QEasingCurve, QObject, QPoint,
                          QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTime,
                          QTimer, QUrl, QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QGuiApplication,
                         QPainter, QPainterPath, QPen, QRegion)
from PyQt6.QtNetwork import (QAbstractSocket, QHostAddress, QNetworkAccessManager,
                             QNetworkInterface, QNetworkReply, QNetworkRequest,
                             QTcpServer, QTcpSocket, QUdpSocket)
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
                             QDialogButtonBox, QFormLayout, QGraphicsOpacityEffect,
                             QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMenu,
                             QMessageBox, QPushButton, QSpinBox,
                             QTabWidget, QTimeEdit, QVBoxLayout, QWidget)

from djs_pyqt6 import (Plugin, Theme, flat_palette,
                       get_theme_colors, is_system_dark, make_num_font, paint_flat_card)

API = None
APP = None
SERVICE = None
DAY_DIALOG = None

VERSION = "2.0.1"
BUILD_VERSION = "20261112B"

DEFAULT_PERIODS = [
    (450, 490), (500, 540), (550, 590), (610, 650), (660, 700),
    (840, 880), (890, 930), (940, 980), (990, 1030), (1140, 1180),
]
DEFAULT_PLAN = "高中方案"
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEK_LABELS = {"all": "每周", "odd": "单周", "even": "双周"}
WEEK_MODES = {"auto": "按周次自动", "odd": "只看单周", "even": "只看双周"}
LESSON_COLORS_DARK = ("#5AA9FF", "#34D399", "#9B7BF0", "#FBBF24", "#F43F5E", "#22D3EE")
LESSON_COLORS_LIGHT = ("#1F6FD0", "#059669", "#6D4AC7", "#D97706", "#E11D48", "#0891B2")
CONTROL_DISCOVERY_PORT = 48690
CONTROL_BASE_PORT = 48700
CONTROL_CODE_TTL = 300.0
CONTROL_PAIR_TIMEOUT = 60.0


def _lesson_color(name, dark):
    palette = LESSON_COLORS_DARK if dark else LESSON_COLORS_LIGHT
    total = 0
    for char in str(name or ""):
        total += ord(char)
    return QColor(palette[total % len(palette)])


def _log(message):
    try:
        if API is not None:
            API.log(str(message))
    except Exception:
        pass


def _fmt_clock(minutes):
    value = int(round(minutes))
    return "%02d:%02d" % (value // 60 % 24, value % 60)


def _fmt_remain(seconds):
    value = max(0, int(round(seconds)))
    hours, rest = divmod(value, 3600)
    mins, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, mins, secs)
    return "%02d:%02d" % (mins, secs)


def _parse_clock(text):
    parts = str(text or "").strip().split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return hour * 60 + minute


def _local_ipv4_list():
    rows = []
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
                if getattr(address.protocol(), "name", "") != "IPv4Protocol":
                    continue
                if address.isLoopback():
                    continue
                text = address.toString()
                if text and text not in rows:
                    rows.append(text)
        except Exception:
            continue
    return rows


def _platform_label(value):
    return {"android": "Android", "windows": "Windows", "macos": "macOS",
            "linux": "Linux"}.get(str(value or "").lower(), "未知设备")


def _state_rev(state):
    raw = json.dumps(state or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


_CLOCK_LOCK = threading.Lock()
_CLOCK_OFFSET = 0.0
_CLOCK_BUSY = False
_CLOCK_INFO = {"ok": False, "at": 0.0, "source": "", "offset": 0.0, "error": "", "rtt": 0.0}


def _now():
    return datetime.now() + timedelta(seconds=_CLOCK_OFFSET)


def clock_info():
    with _CLOCK_LOCK:
        return dict(_CLOCK_INFO)


def clock_offset():
    return _CLOCK_OFFSET


_CLOCK_SOURCES = (
    ("苏宁", "https://f.m.suning.com/api/ct.do", "suning"),
    ("腾讯", "https://vv.video.qq.com/checktime?otype=json", "qq"),
    ("百度", "https://www.baidu.com", "date"),
    ("淘宝", "https://api.m.taobao.com/rest/api3.do?api=mtop.common.getTimestamp", "taobao"),
)


def _apply_clock_offset(offset, source, rtt):
    global _CLOCK_OFFSET, _CLOCK_BUSY
    with _CLOCK_LOCK:
        _CLOCK_OFFSET = float(offset)
        _CLOCK_INFO.update({"ok": True, "at": time.time() + float(offset), "source": source,
                            "offset": float(offset), "error": "", "rtt": float(rtt)})
        _CLOCK_BUSY = False
    _log("ZX 网络校时成功 %.2fs · %s" % (float(offset), source))


def _clock_fail(message):
    global _CLOCK_BUSY
    with _CLOCK_LOCK:
        _CLOCK_INFO.update({"ok": False, "error": str(message or "时间接口不可用")})
        _CLOCK_BUSY = False
    _log("ZX 网络校时失败: %s" % message)


def _seconds_from_number(value):
    try:
        number = float(value)
    except Exception:
        return None
    if number <= 0:
        return None
    return number / 1000.0 if number > 1e11 else number


def _epoch_from_payload(kind, body, reply):
    if kind == "suning":
        return _seconds_from_number((json.loads(body) or {}).get("currentTime"))
    if kind == "qq":
        match = re.search(r'"t"\s*:\s*"?(\d{9,16})', body)
        return _seconds_from_number(match.group(1)) if match else None
    if kind == "taobao":
        data = json.loads(body) or {}
        return _seconds_from_number((data.get("data") or {}).get("t"))
    if kind == "date":
        raw = bytes(reply.rawHeader(QByteArray(b"Date"))).decode("ascii", "ignore")
        if not raw:
            return None
        return parsedate_to_datetime(raw).timestamp()
    return None


def sync_clock_async():
    try:
        service = _service()
    except Exception:
        service = None
    if service is None:
        return False
    return service.sync_time()


def clock_status_text():
    info = clock_info()
    if info.get("ok"):
        offset = float(info.get("offset") or 0.0)
        sign = "+" if offset >= 0 else "-"
        return "已校时 %s%.2f 秒 · %s" % (sign, abs(offset), info.get("source") or "网络")
    if info.get("error"):
        return "校时失败，使用本机时间"
    return "尚未校时"


def _ui_font(size, bold=False):
    font = QFont("Microsoft YaHei")
    font.setPixelSize(max(8, int(size)))
    font.setBold(bold)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def _num_font(size):
    return make_num_font(pixel_size=max(9, int(size)))


def _theme_dark_widget(widget):
    probe = widget
    while probe is not None:
        mode = str(getattr(probe, "theme_mode", "system") or "system").lower()
        if mode == "dark":
            return True
        if mode == "light":
            return False
        if not hasattr(probe, "parentWidget"):
            break
        probe = probe.parentWidget()
    theme = getattr(APP, "theme", None)
    if theme is not None and hasattr(theme, "is_dark"):
        try:
            return bool(theme.is_dark)
        except Exception:
            pass
    try:
        return bool(is_system_dark())
    except Exception:
        return False


def _theme_colors_of(dark):
    try:
        return get_theme_colors(Theme("ZX", bool(dark))) or {}
    except Exception:
        return {}


def _state_colors(dark):
    colors = _theme_colors_of(dark)
    return {
        "accent": QColor(colors.get("accent") or "#FBBF24"),
        "warn": QColor("#FBBF24" if dark else "#D97706"),
        "danger": QColor(colors.get("danger") or "#F43F5E"),
        "success": QColor("#34D399" if dark else "#059669"),
        "purple": QColor("#9B7BF0" if dark else "#6D4AC7"),
        "blue": QColor("#5AA9FF" if dark else "#1F6FD0"),
    }


def _elide(font, text, width):
    metrics = QFontMetricsF(font)
    return metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, max(0.0, float(width)))


def _sample_entries():
    rows = [
        (1, 0, "语文", "高一(1)班"), (1, 1, "数学", "高一(1)班"), (1, 2, "英语", "高一(1)班"),
        (1, 3, "物理", "物理实验室"), (1, 4, "化学", "化学实验室"),
        (2, 0, "数学", "高一(1)班"), (2, 1, "语文", "高一(1)班"), (2, 2, "英语", "高一(1)班"),
        (2, 3, "生物", "生物实验室"), (2, 4, "政治", "高一(1)班"),
        (3, 0, "英语", "高一(1)班"), (3, 1, "数学", "高一(1)班"), (3, 2, "物理", "物理实验室"),
        (3, 3, "化学", "化学实验室"), (3, 4, "历史", "高一(1)班"),
        (4, 0, "语文", "高一(1)班"), (4, 1, "数学", "高一(1)班"), (4, 2, "生物", "生物实验室"),
        (4, 3, "地理", "高一(1)班"), (4, 4, "体育", "操场"),
        (5, 0, "数学", "高一(1)班"), (5, 1, "英语", "高一(1)班"), (5, 2, "物理", "物理实验室"),
        (5, 3, "化学", "化学实验室"), (5, 4, "自习", "高一(1)班"),
    ]
    entries = [
        {"day": day, "period": period, "name": name, "room": room, "weeks": "all"}
        for day, period, name, room in rows
    ]
    entries.append({"day": 1, "period": 0, "name": "升旗仪式", "room": "升旗广场",
                    "weeks": "all", "kind": "activity", "start": 430, "end": 450})
    for day in range(1, 6):
        entries.append({"day": day, "period": 3, "name": "大课间", "room": "操场",
                        "weeks": "all", "kind": "activity", "start": 590, "end": 610})
    return entries


class ZxStore:
    def __init__(self):
        self.data = self._defaults()
        self.load()

    def _defaults(self):
        return {
            "schema": 2,
            "plans": {DEFAULT_PLAN: _sample_entries()},
            "active": DEFAULT_PLAN,
            "periods": [list(item) for item in DEFAULT_PERIODS],
            "week_mode": "auto",
            "semester_start": "",
            "overrides": {},
            "control": {"enabled": False, "host_id": "", "name": "", "devices": []},
            "ui": {"island": True, "remind_min": 2, "time_sync": True},
        }

    def load(self):
        raw = None
        try:
            raw = API.get_config("state", None) if API is not None else None
        except Exception:
            raw = None
        if isinstance(raw, dict):
            for key in ("schema", "plans", "active", "periods", "week_mode", "semester_start",
                        "overrides", "lan", "control", "ui"):
                if key in raw and raw[key] is not None:
                    self.data[key] = raw[key]
        self._normalize()

    def _normalize(self):
        if int(self.data.get("schema") or 1) < 2:
            old = self.data.get("plans")
            names = []
            if isinstance(old, dict):
                for group in old.values():
                    if isinstance(group, list):
                        names.extend(str(item.get("name") or "") for item in group if isinstance(item, dict))
            if "高等数学" in names:
                self.data["plans"] = {DEFAULT_PLAN: _sample_entries()}
                self.data["active"] = DEFAULT_PLAN
            self.data["schema"] = 2
        plans = self.data.get("plans")
        if not isinstance(plans, dict) or not plans:
            plans = {DEFAULT_PLAN: _sample_entries()}
            self.data["plans"] = plans
        clean_plans = {}
        for name, entries in plans.items():
            items = []
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    try:
                        day = int(entry.get("day", 1))
                        period = int(entry.get("period", 0))
                    except Exception:
                        continue
                    if day < 1 or day > 7 or period < 0:
                        continue
                    weeks = str(entry.get("weeks") or "all")
                    if weeks not in WEEK_LABELS:
                        weeks = "all"
                    item = {
                        "day": day,
                        "period": period,
                        "name": str(entry.get("name") or "未命名"),
                        "room": str(entry.get("room") or ""),
                        "weeks": weeks,
                        "kind": "activity" if str(entry.get("kind") or "") == "activity" else "lesson",
                    }
                    if item["kind"] == "activity":
                        try:
                            item["start"] = int(entry.get("start"))
                            item["end"] = int(entry.get("end"))
                        except Exception:
                            continue
                        if not 0 <= item["start"] < item["end"] <= 1439:
                            continue
                    elif entry.get("start") is not None and entry.get("end") is not None:
                        try:
                            start_at = int(entry.get("start"))
                            end_at = int(entry.get("end"))
                        except Exception:
                            start_at = end_at = None
                        if start_at is not None and end_at is not None and 0 <= start_at < end_at <= 1439:
                            item["start"] = start_at
                            item["end"] = end_at
                    items.append(item)
            clean_plans[str(name or DEFAULT_PLAN)] = items
        self.data["plans"] = clean_plans
        active = str(self.data.get("active") or "")
        if active not in clean_plans:
            active = sorted(clean_plans.keys())[0]
        self.data["active"] = active
        periods = []
        for item in self.data.get("periods") or []:
            try:
                start = int(item[0])
                end = int(item[1])
            except Exception:
                continue
            if 0 <= start < end <= 1439:
                periods.append([start, end])
        if not periods:
            periods = [list(item) for item in DEFAULT_PERIODS]
        self.data["periods"] = periods
        mode = str(self.data.get("week_mode") or "auto")
        self.data["week_mode"] = mode if mode in WEEK_MODES else "auto"
        start = str(self.data.get("semester_start") or "")
        if start:
            try:
                datetime.strptime(start, "%Y-%m-%d")
            except Exception:
                start = ""
        self.data["semester_start"] = start
        overrides = self.data.get("overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        self.data["overrides"] = {
            str(key): value for key, value in overrides.items() if isinstance(value, list)
        }
        lan = self.data.get("lan")
        if not isinstance(lan, dict):
            lan = {}
        control = self.data.get("control")
        if not isinstance(control, dict):
            control = {}
        control["enabled"] = bool(control.get("enabled"))
        name = str(control.get("name") or "").strip()
        if not name:
            name = str(lan.get("name") or "").strip()
        if not name:
            name = "ZX-%04d" % random.randint(0, 9999)
        control["name"] = name[:40]
        self.data.pop("lan", None)
        host_id = str(control.get("host_id") or "").strip()
        if not host_id:
            host_id = "%08x" % random.getrandbits(32)
        control["host_id"] = host_id[:64]
        devices = []
        for item in control.get("devices") or []:
            if not isinstance(item, dict):
                continue
            device_id = str(item.get("id") or "").strip()
            token = str(item.get("token") or "").strip()
            if not device_id or not token:
                continue
            try:
                paired_at = int(item.get("paired_at") or 0)
            except Exception:
                paired_at = 0
            try:
                last_seen = int(item.get("last_seen") or 0)
            except Exception:
                last_seen = 0
            devices.append({
                "id": device_id[:64],
                "name": str(item.get("name") or "设备")[:40],
                "platform": str(item.get("platform") or "unknown")[:16],
                "token": token[:64],
                "paired_at": paired_at,
                "last_seen": last_seen,
            })
        control["devices"] = devices
        self.data["control"] = control

    def save(self):
        try:
            if API is not None:
                API.set_config("state", self.data)
        except Exception:
            _log("ZX 保存配置失败")


class ZxSchedule:
    def __init__(self, store):
        self.store = store

    def periods(self):
        return [tuple(item) for item in self.store.data.get("periods") or DEFAULT_PERIODS]

    def _parity(self, day):
        mode = self.store.data.get("week_mode", "auto")
        if mode == "odd":
            return 1
        if mode == "even":
            return 0
        start = self.store.data.get("semester_start") or ""
        if start:
            try:
                begin = datetime.strptime(start, "%Y-%m-%d").date()
                week = ((day - begin).days // 7) + 1
                return week % 2
            except Exception:
                pass
        return day.isocalendar()[1] % 2

    def _week_match(self, entry, day):
        weeks = str(entry.get("weeks") or "all")
        if weeks == "all":
            return True
        parity = self._parity(day)
        return parity == 1 if weeks == "odd" else parity == 0

    def lessons_for(self, day):
        key = day.strftime("%Y-%m-%d")
        overrides = self.store.data.get("overrides") or {}
        if key in overrides:
            raw = overrides.get(key) or []
        else:
            plan = self.store.data.get("plans", {}).get(self.store.data.get("active"), [])
            raw = [
                entry for entry in plan
                if int(entry.get("day", 0) or 0) == day.isoweekday() and self._week_match(entry, day)
            ]
        periods = self.periods()
        items = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            try:
                index = int(entry.get("period", 0))
            except Exception:
                index = 0
            kind = "activity" if str(entry.get("kind") or "") == "activity" else "lesson"
            if index < 0 or index >= len(periods):
                if kind != "activity":
                    continue
                start, end = periods[0] if periods else (450, 490)
            else:
                start, end = periods[index]
            try:
                custom_start = int(entry.get("start"))
                custom_end = int(entry.get("end"))
            except Exception:
                custom_start = custom_end = None
            if custom_start is not None and custom_end is not None and 0 <= custom_start < custom_end <= 1439:
                start, end = custom_start, custom_end
            items.append({
                "period": index,
                "kind": kind,
                "start": start,
                "end": end,
                "name": str(entry.get("name") or "未命名"),
                "room": str(entry.get("room") or ""),
                "weeks": str(entry.get("weeks") or "all"),
            })
        items.sort(key=lambda item: item["start"])
        return items

    def snapshot(self, now=None):
        now = now or _now()
        today = now.date()
        current_minute = now.hour * 60 + now.minute + now.second / 60.0 + now.microsecond / 60000000.0
        lessons = self.lessons_for(today)
        current = None
        for item in lessons:
            if item["start"] <= current_minute < item["end"]:
                current = item
                break
        previous = None
        for item in lessons:
            if item["end"] <= current_minute:
                previous = item
        next_item = None
        for item in lessons:
            if item["start"] > current_minute:
                next_item = item
                break
        offset = 0
        if current is None and next_item is None:
            for step in range(1, 8):
                probe = today + timedelta(days=step)
                items = self.lessons_for(probe)
                if items:
                    next_item = dict(items[0])
                    next_item["day_offset"] = step
                    offset = step
                    break
        if current is not None:
            state = "class"
            total = max(1.0, float(current["end"] - current["start"]))
            remain = max(0.0, (current["end"] - current_minute) * 60.0)
            progress = max(0.0, min(1.0, (current_minute - current["start"]) / total))
            later = None
            for item in lessons:
                if item["start"] >= current["end"]:
                    later = item
                    break
            next_item = later
        elif next_item is not None and offset == 0:
            state = "break"
            base = previous["end"] if previous else max(0.0, next_item["start"] - 10.0)
            span = max(1.0, float(next_item["start"] - base))
            remain = max(0.0, (next_item["start"] - current_minute) * 60.0)
            progress = 1.0 - max(0.0, min(1.0, remain / 60.0 / span))
        else:
            state = "free"
            remain = 0.0
            progress = 0.0
        return {
            "now": now,
            "today": today,
            "weekday": WEEKDAY_NAMES[today.weekday()],
            "lessons": lessons,
            "state": state,
            "current": current,
            "prev": previous,
            "next": next_item,
            "next_offset": offset,
            "remain": remain,
            "progress": progress,
        }


def _css_rgba(color):
    value = QColor(color)
    return "rgba(%d,%d,%d,%d)" % (value.red(), value.green(), value.blue(), value.alpha())


def _next_when(snap, item):
    offset = int(item.get("day_offset", 0) or 0)
    if offset <= 0:
        return "今天"
    if offset == 1:
        return "明天"
    probe = snap["today"] + timedelta(days=offset)
    return WEEKDAY_NAMES[probe.weekday()]


def _animate_dialog_show(dialog):
    target = dialog.pos()
    fade = QPropertyAnimation(dialog, b"windowOpacity", dialog)
    fade.setDuration(180)
    fade.setEasingCurve(QEasingCurve.Type.OutCubic)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    slide = QPropertyAnimation(dialog, b"pos", dialog)
    slide.setDuration(220)
    slide.setEasingCurve(QEasingCurve.Type.OutCubic)
    slide.setStartValue(target - QPoint(0, 10))
    slide.setEndValue(target)
    dialog.setWindowOpacity(0.0)
    dialog.move(slide.startValue())
    fade.start()
    slide.start()


class ZxScheduleWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_mode = "system"
        self.setMinimumSize(220, 132)
        self.setMouseTracking(True)
        self._rs_edge = None
        self._rs_origin = QPoint()
        self._rs_rect = QRect()
        self._rs_last = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.update)
        self._frame = QTimer(self)
        self._frame.setInterval(80)
        self._frame.timeout.connect(self.update)
        self._appear = 1.0
        self._hover = 0.0
        self._pulse = 0.0
        self._key = None
        self._appear_anim = QVariantAnimation(self)
        self._appear_anim.setDuration(420)
        self._appear_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._appear_anim.valueChanged.connect(self._on_appear)
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(160)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover)

    def _on_appear(self, value):
        self._appear = float(value)
        self.update()

    def _on_hover(self, value):
        self._hover = float(value)
        self.update()

    def _animate_hover(self, target):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover)
        self._hover_anim.setEndValue(float(target))
        self._hover_anim.start()

    def enterEvent(self, event):
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def sizeHint(self):
        return QSize(300, 168)

    def showEvent(self, event):
        super().showEvent(event)
        self._timer.start()
        self._frame.start()
        self._apply_window_mask()
        QTimer.singleShot(0, self._apply_window_mask)
        self._appear = 0.0
        self._appear_anim.stop()
        self._appear_anim.setStartValue(0.0)
        self._appear_anim.setEndValue(1.0)
        self._appear_anim.start()
        self.update()

    def hideEvent(self, event):
        self._timer.stop()
        self._frame.stop()
        super().hideEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_window_mask()

    def _apply_window_mask(self):
        win = self.window()
        if win is None or win is self:
            return
        width = win.width()
        height = win.height()
        if width <= 2 or height <= 2:
            return
        radius = min(18.0, min(width, height) * 0.13)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.0, 0.0, float(width), float(height)), radius, radius)
        win.setMask(QRegion(path.toFillPolygon().toPolygon()))

    def set_theme_mode(self, mode):
        value = str(mode or "").lower()
        self.theme_mode = value if value in ("dark", "light") else "system"
        self.update()

    def _snapshot(self):
        try:
            return _service().model.snapshot()
        except Exception:
            return None

    def _resize_edge_at(self, pos):
        m = 7
        w, h = self.width(), self.height()
        if w < m * 4 or h < m * 4:
            return None
        left = pos.x() <= m
        right = pos.x() >= w - m
        top = pos.y() <= m
        bottom = pos.y() >= h - m
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bottom and left:
            return "bl"
        if bottom and right:
            return "br"
        if left:
            return "l"
        if right:
            return "r"
        if top:
            return "t"
        if bottom:
            return "b"
        return None

    def _apply_remote_resize(self, gp, final=False):
        if not self._rs_edge or self._rs_rect.isNull():
            return
        dx = gp.x() - self._rs_origin.x()
        dy = gp.y() - self._rs_origin.y()
        g = self._rs_rect
        minw, minh = 220, 132
        x, y, w, h = g.x(), g.y(), g.width(), g.height()
        if "l" in self._rs_edge:
            w = max(minw, g.width() - dx)
            x = g.x() + g.width() - w
        elif "r" in self._rs_edge:
            w = max(minw, g.width() + dx)
        if "t" in self._rs_edge:
            h = max(minh, g.height() - dy)
            y = g.y() + g.height() - h
        elif "b" in self._rs_edge:
            h = max(minh, g.height() + dy)
        if not final and self._rs_last == (x, y, w, h):
            return
        self._rs_last = (x, y, w, h)
        try:
            if API is not None and hasattr(API, "resize_float_widget"):
                API.resize_float_widget(self, w, h, x, y, final)
        except Exception:
            pass

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._resize_edge_at(event.position().toPoint())
            if edge:
                self._rs_edge = edge
                self._rs_origin = event.globalPosition().toPoint()
                self._rs_rect = QRect(self.mapToGlobal(QPoint(0, 0)), self.size())
                self._rs_last = None
                event.accept()
                return
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._rs_edge is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._apply_remote_resize(event.globalPosition().toPoint())
            event.accept()
            return
        edge = self._resize_edge_at(event.position().toPoint())
        cursors = {
            "l": Qt.CursorShape.SizeHorCursor, "r": Qt.CursorShape.SizeHorCursor,
            "t": Qt.CursorShape.SizeVerCursor, "b": Qt.CursorShape.SizeVerCursor,
            "tl": Qt.CursorShape.SizeFDiagCursor, "br": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor, "bl": Qt.CursorShape.SizeBDiagCursor,
        }
        self.setCursor(cursors.get(edge, Qt.CursorShape.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._rs_edge is not None:
            self._apply_remote_resize(event.globalPosition().toPoint(), True)
            self._rs_edge = None
            self._rs_rect = QRect()
            self._rs_last = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            open_day_dialog()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _remove_self(self):
        try:
            if API is not None and hasattr(API, "remove_float_widget"):
                API.remove_float_widget(self)
                return
        except Exception:
            pass
        win = self.window()
        if win is not None and win is not self:
            win.hide()

    def contextMenuEvent(self, event):
        pal = flat_palette(_theme_dark_widget(self))
        theme = _theme_colors_of(pal["dark"])
        menu = QMenu(self)
        panel = theme.get("panel_bg") or _css_rgba(pal["surface"])
        alternate = theme.get("alternate_bg") or panel
        border = theme.get("border_color") or _css_rgba(pal["line"])
        menu.setStyleSheet(
            "QMenu{background:%s;color:%s;border:1px solid %s;padding:4px;}"
            "QMenu::item{padding:6px 22px 6px 14px;border-radius:4px;}"
            "QMenu::item:selected{background:%s;color:%s;}"
            "QMenu::separator{height:1px;background:%s;margin:4px 8px;}"
            % (panel, pal["ink"].name(), border, alternate, pal["ink"].name(), border)
        )
        act_today = menu.addAction("今日课表")
        menu.addSeparator()
        store = _service().store
        plan_menu = menu.addMenu("切换方案")
        for name in sorted(store.data.get("plans", {}).keys()):
            action = plan_menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(name == store.data.get("active"))
            action.triggered.connect(lambda _checked=False, value=name: self._switch_plan(value))
        menu.addSeparator()
        act_refresh = menu.addAction("立即刷新")
        menu.addSeparator()
        act_remove = menu.addAction("移除此控件")
        chosen = menu.exec(event.globalPos())
        if chosen is act_today:
            open_day_dialog()
        elif chosen is act_refresh:
            self.update()
        elif chosen is act_remove:
            self._remove_self()

    def _switch_plan(self, name):
        service = _service()
        service.store.data["active"] = name
        service.store.save()
        self.update()

    def _text(self, painter, rect, font, color, text, align=None):
        painter.setFont(font)
        painter.setPen(QPen(color))
        flags = int(align if align is not None else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        painter.drawText(rect, flags, str(text))

    def _paint_tag(self, painter, rect, color, text):
        tint = QColor(color)
        tint.setAlpha(30)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint)
        painter.drawRoundedRect(rect, 4.0, 4.0)
        self._text(painter, rect, _ui_font(max(9.5, rect.height() * 0.58)), color, text,
                   Qt.AlignmentFlag.AlignCenter)

    def _paint_head(self, painter, pad, width, height, pal, tone, kicker, clock):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tone)
        bar_w = max(2.5, width * 0.012)
        bar_h = max(12.0, height * 0.12)
        painter.drawRoundedRect(QRectF(pad, pad, bar_w, bar_h), bar_w * 0.5, bar_w * 0.5)
        kicker_font = _ui_font(max(10.0, height * 0.068), True)
        kicker_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        clock_font = _num_font(max(10.0, height * 0.070))
        offset = 0.0
        if getattr(self, "_live", False):
            dot = QColor(tone)
            dot.setAlpha(int(90 + 150 * self._pulse))
            painter.setBrush(dot)
            painter.drawEllipse(QPointF(pad + bar_w + 7.0, pad + 7.0), 3.0, 3.0)
            offset = 14.0
        self._text(painter, QRectF(pad + bar_w + 7.0 + offset, pad - 1.0,
                                   width - pad * 2.0 - bar_w - 7.0 - offset - 46.0, 18.0),
                   kicker_font, pal["dim"], kicker)
        self._text(painter, QRectF(pad, pad - 1.0, width - pad * 2.0, 18.0),
                   clock_font, pal["dim"], clock,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _paint_progress(self, painter, pad, width, y, ratio, tone, pal):
        track = QRectF(pad, y, width - pad * 2.0, 5.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pal["track"])
        painter.drawRoundedRect(track, 2.5, 2.5)
        value = max(0.0, min(1.0, float(ratio)))
        if value <= 0.0:
            return
        fill = QRectF(track.left(), track.top(), max(4.0, track.width() * value), track.height())
        painter.setBrush(tone)
        painter.drawRoundedRect(fill, 2.5, 2.5)

    def _paint_footer(self, painter, label, item, when, use_start, pad, width, height, pal):
        y = height * 0.715
        painter.setPen(QPen(pal["line"], 1.0))
        painter.drawLine(QPointF(pad, y), QPointF(width - pad, y))
        top = y + 9.0
        label_font = _ui_font(max(9.5, height * 0.058))
        self._text(painter, QRectF(pad, top, 34.0, 18.0), label_font, pal["dim"], label)
        if item is None:
            self._text(painter, QRectF(pad + 34.0, top, width - pad * 2.0 - 34.0, 18.0),
                       _ui_font(max(11.0, height * 0.070)), pal["dim"], when)
            return
        value_font = _ui_font(max(11.0, height * 0.070), True)
        tail_font = _ui_font(max(9.5, height * 0.058))
        tail = "%s %s" % (when, _fmt_clock(item.get("start") if use_start else item.get("end")))
        tail_width = QFontMetricsF(tail_font).horizontalAdvance(tail) + 6.0
        name_width = max(20.0, width - pad * 2.0 - 34.0 - tail_width)
        self._text(painter, QRectF(pad + 34.0, top, name_width, 18.0), value_font, pal["ink"],
                   _elide(value_font, item.get("name", ""), name_width))
        self._text(painter, QRectF(pad, top, width - pad * 2.0, 18.0), tail_font, pal["dim"], tail,
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _paint_lesson(self, painter, snap, item, tone, kicker, meta_left, remain,
                      footer_label, footer_item, footer_when, footer_use_start,
                      pad, width, height, pal, colors):
        self._paint_head(painter, pad, width, height, pal, tone, kicker,
                         _fmt_clock(snap["now"].hour * 60 + snap["now"].minute))
        title_font = _ui_font(max(16.0, height * 0.143), True)
        title_top = pad + 17.0
        text_x = pad + max(2.5, width * 0.012) + 7.0
        room_width = 0.0
        if item.get("room"):
            room_font = _ui_font(max(9.5, height * 0.062))
            room_width = QFontMetricsF(room_font).horizontalAdvance(item["room"]) + 12.0
        title_width = max(24.0, width - pad * 2.0 - (text_x - pad) - room_width - 6.0)
        if item.get("room"):
            self._paint_tag(painter, QRectF(width - pad - room_width, title_top + 6.0, room_width, 18.0),
                            tone, item["room"])
        self._text(painter, QRectF(text_x, title_top, title_width, height * 0.19), title_font,
                   pal["ink"], _elide(title_font, item.get("name", ""), title_width))
        self._paint_progress(painter, pad, width, height * 0.465, snap["progress"], tone, pal)
        self._text(painter, QRectF(pad, height * 0.465 + 11.0, width * 0.55, 18.0),
                   _ui_font(max(10.0, height * 0.063)), pal["dim"], meta_left)
        remain_font = _num_font(max(13.0, height * 0.105))
        self._text(painter, QRectF(pad, height * 0.465 + 8.0, width - pad * 2.0 - 28.0, 20.0),
                   remain_font, tone, _fmt_remain(remain),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._text(painter, QRectF(pad, height * 0.465 + 11.0, width - pad * 2.0, 18.0),
                   _ui_font(max(9.5, height * 0.058)), pal["dim"], "剩余",
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._paint_footer(painter, footer_label, footer_item, footer_when, footer_use_start,
                           pad, width, height, pal)

    def paintEvent(self, event):
        width = self.width()
        height = self.height()
        if width < 60 or height < 60:
            return
        dark = _theme_dark_widget(self)
        pal = flat_palette(dark)
        colors = _state_colors(dark)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        radius = min(18.0, min(width, height) * 0.13)
        paint_flat_card(painter, QRectF(0.5, 0.5, width - 1.0, height - 1.0), radius, pal)
        if self._hover > 0.01:
            glow = QColor(pal["line"])
            glow.setAlpha(int(70 + 90 * self._hover))
            painter.setPen(QPen(glow, 1.0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(1.2, 1.2, width - 2.4, height - 2.4),
                                    max(6.0, radius - 0.8), max(6.0, radius - 0.8))
        pad = max(12.0, min(width, height) * 0.085)
        snap = self._snapshot()
        if snap is None:
            self._text(painter, QRectF(pad, pad, width - pad * 2.0, height - pad * 2.0),
                       _ui_font(13.0), pal["dim"], "正在准备课程表")
            painter.end()
            return
        anchor = snap["current"] if snap["state"] == "class" else snap["next"]
        key = (snap["state"], snap["today"].isoformat(),
               (anchor or {}).get("day"), (anchor or {}).get("period"),
               str((anchor or {}).get("name") or ""))
        if key != self._key:
            self._key = key
            if self.isVisible() and self._appear >= 1.0:
                self._appear = 0.0
                self._appear_anim.stop()
                self._appear_anim.setStartValue(0.0)
                self._appear_anim.setEndValue(1.0)
                self._appear_anim.start()
        self._pulse = 0.5 + 0.5 * math.sin(time.monotonic() * 3.4)
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, self._appear)))
        painter.translate(0.0, (1.0 - self._appear) * 5.0)
        state = snap["state"]
        self._live = state == "class"
        if state == "class":
            item = snap["current"]
            remain = snap["remain"]
            tone = _lesson_color(item.get("name"), dark)
            if remain <= 120:
                tone = colors["danger"]
            elif remain <= 300:
                tone = colors["warn"]
            self._paint_lesson(
                painter, snap, item, tone,
                ("活动 · %s" % _fmt_clock(item["start"])) if item.get("kind") == "activity"
                else "本节课 · 第 %d 节" % (item["period"] + 1),
                "%s 下课" % _fmt_clock(item["end"]), remain,
                "下节", snap["next"], _next_when(snap, snap["next"]) if snap["next"] else "今日课程已结束",
                True, pad, width, height, pal, colors)
        elif state == "break":
            item = snap["next"]
            remain = snap["remain"]
            tone = colors["warn"] if remain <= 120 else colors["accent"]
            prev = snap["prev"]
            kicker = ("课间 · %s 后" % prev.get("name")) if prev and prev.get("kind") == "activity" else (
                "课间 · 第 %d 节后" % (prev["period"] + 1) if prev else "今天 · 第一节课前")
            self._paint_lesson(
                painter, snap, item, tone, kicker, "%s 开始" % _fmt_clock(item["start"]), remain,
                "上一节", prev, "", False, pad, width, height, pal, colors)
        else:
            self._paint_free(painter, snap, pad, width, height, pal, colors)
        painter.restore()
        painter.end()

    def _paint_free(self, painter, snap, pad, width, height, pal, colors):
        tone = colors["accent"]
        self._paint_head(painter, pad, width, height, pal, tone, "今天 · %s" % snap["weekday"],
                         _fmt_clock(snap["now"].hour * 60 + snap["now"].minute))
        title_font = _ui_font(max(17.0, height * 0.148), True)
        text_x = pad + max(2.5, width * 0.012) + 7.0
        self._text(painter, QRectF(text_x, pad + 17.0, width - pad * 2.0 - (text_x - pad), height * 0.19),
                   title_font, pal["ink"], "现在没有课")
        sub = "今天的课程已经结束" if snap["lessons"] else "今天没有课程安排"
        self._text(painter, QRectF(text_x, pad + 17.0 + height * 0.20, width - pad * 2.0 - (text_x - pad), 20.0),
                   _ui_font(max(10.5, height * 0.066)), pal["dim"], sub)
        nxt = snap["next"]
        if nxt is None:
            self._paint_footer(painter, "下一节", None, "接下来一周没有课程", True, pad, width, height, pal)
        else:
            self._paint_footer(painter, "下一节", nxt, _next_when(snap, nxt), True, pad, width, height, pal)


class ZxDayDialog(QWidget):
    def __init__(self, day=None):
        super().__init__(None)
        self._day = day or _now().date()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFixedWidth(340)
        self._labels = []
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._build()
        self._apply_theme()
        self._reposition()
        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(1500)
        self._theme_timer.timeout.connect(self._sync_theme)
        self._theme_timer.start()
        self._dark = _theme_dark_widget(self)

    def showEvent(self, event):
        super().showEvent(event)
        target = self.pos()
        self.setWindowOpacity(0.0)
        self._fade.stop()
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._slide.stop()
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._slide.setStartValue(target - QPoint(0, 12))
        self._slide.setEndValue(target)
        self._slide.start()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)
        body = QVBoxLayout()
        body.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(8)
        self.lbl_title = QLabel(self)
        self.lbl_title.setFont(_ui_font(15, True))
        head.addWidget(self.lbl_title)
        head.addStretch(1)
        self.btn_close = QPushButton("×", self)
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close)
        head.addWidget(self.btn_close)
        body.addLayout(head)
        self.lesson_box = QVBoxLayout()
        self.lesson_box.setSpacing(8)
        body.addLayout(self.lesson_box)
        self.lbl_hint = QLabel("双击浮窗可随时查看当天课程", self)
        self.lbl_hint.setFont(_ui_font(10))
        body.addWidget(self.lbl_hint)
        outer.addLayout(body)
        self._fill_lessons()

    def _fill_lessons(self):
        while self.lesson_box.count():
            item = self.lesson_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        try:
            lessons = _service().model.lessons_for(self._day)
        except Exception:
            lessons = []
        for lesson in lessons:
            row = QWidget(self)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(10)
            index = QLabel("活动" if lesson.get("kind") == "activity" else "第 %d 节" % (lesson["period"] + 1), row)
            index.setFixedWidth(52)
            index.setFont(_ui_font(10))
            time_label = QLabel("%s - %s" % (_fmt_clock(lesson["start"]), _fmt_clock(lesson["end"])), row)
            time_label.setFixedWidth(88)
            time_label.setFont(_num_font(10))
            name = QLabel(lesson["name"], row)
            name.setFont(_ui_font(12, True))
            room = QLabel(lesson["room"] or "", row)
            room.setFont(_ui_font(10))
            lay.addWidget(index)
            lay.addWidget(time_label)
            lay.addWidget(name, 1)
            lay.addWidget(room)
            self.lesson_box.addWidget(row)
            self._labels.append((index, "dim"))
            self._labels.append((time_label, "dim"))
            self._labels.append((name, "ink"))
            self._labels.append((room, "dim"))
        if not lessons:
            empty = QLabel("今天没有课程", self)
            empty.setFont(_ui_font(12))
            self.lesson_box.addWidget(empty)
            self._labels.append((empty, "dim"))
        self.lbl_title.setText("%d 月 %d 日 · %s" % (self._day.month, self._day.day,
                                                     WEEKDAY_NAMES[self._day.weekday()]))

    def _apply_theme(self):
        dark = _theme_dark_widget(self)
        self._dark = dark
        pal = flat_palette(dark)
        colors = _theme_colors_of(dark)
        accent = colors.get("accent") or "#FBBF24"
        self.lbl_title.setStyleSheet("color:%s;" % pal["ink"].name())
        self.lbl_hint.setStyleSheet("color:%s;" % _css_rgba(pal["dim"]))
        self.btn_close.setStyleSheet(
            "QPushButton{background:%s;color:%s;border:none;border-radius:12px;font-size:15px;}"
            "QPushButton:hover{background:%s;color:%s;}"
            % (_css_rgba(pal["track"]), pal["ink"].name(), _css_rgba(QColor(accent)), pal["ink"].name())
        )
        for label, role in self._labels:
            label.setStyleSheet("color:%s;" % (pal["ink"].name() if role == "ink" else _css_rgba(pal["dim"])))
        self.update()

    def _sync_theme(self):
        if _theme_dark_widget(self) != self._dark:
            self._apply_theme()

    def _reposition(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        height = self.sizeHint().height()
        self.setFixedHeight(max(160, height))
        self.move(area.center().x() - self.width() // 2, area.top() + 96)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        paint_flat_card(painter, QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0),
                        14.0, flat_palette(self._dark))
        painter.end()

    def closeEvent(self, event):
        global DAY_DIALOG
        self._theme_timer.stop()
        if DAY_DIALOG is self:
            DAY_DIALOG = None
        super().closeEvent(event)


def open_day_dialog(day=None):
    global DAY_DIALOG
    try:
        if DAY_DIALOG is not None:
            DAY_DIALOG.close()
    except Exception:
        pass
    DAY_DIALOG = ZxDayDialog(day)
    DAY_DIALOG.show()
    DAY_DIALOG.raise_()


class ZxIsland(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.theme_mode = "system"
        self._title = ""
        self._body = ""
        self._tone = "accent"
        self._expanded = False
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._dismiss)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(200)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade)
        self._slide = QPropertyAnimation(self, b"pos", self)
        self._slide.setDuration(320)
        self._slide.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._size_anim = QPropertyAnimation(self, b"geometry", self)
        self._size_anim.setDuration(260)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._tick = QTimer(self)
        self._tick.setInterval(90)
        self._tick.timeout.connect(self.update)
        self._dismissing = False
        self._shown_at = 0.0
        self._duration = 6.5
        self.resize(240, 44)

    def show_notice(self, title, body, tone="accent", sticky=False):
        self._title = str(title or "")
        self._body = str(body or "")
        self._tone = str(tone or "accent")
        self._expanded = True
        self._dismissing = False
        self._duration = 11.0 if sticky else 6.5
        self._shown_at = time.monotonic()
        self._reposition()
        target = self.pos()
        self.move(target.x(), target.y() - 18)
        self.show()
        self.raise_()
        self._slide.stop()
        self._slide.setStartValue(QPoint(target.x(), target.y() - 18))
        self._slide.setEndValue(target)
        self._slide.start()
        self.setWindowOpacity(0.0)
        self._fade.stop()
        self._fade.setDuration(220)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._tick.start()
        self._hide_timer.start(int(self._duration * 1000))

    def _on_fade(self):
        if self._dismissing:
            self._dismissing = False
            self._tick.stop()
            self.hide()

    def _tone_color(self, colors):
        return {
            "danger": colors["danger"],
            "warn": colors["warn"],
            "success": colors["success"],
            "message": colors["blue"],
            "purple": colors["purple"],
        }.get(self._tone, colors["accent"])

    def _target_size(self):
        title_font = _ui_font(13, True)
        body_font = _ui_font(11)
        title_width = QFontMetricsF(title_font).horizontalAdvance(self._title)
        body_width = QFontMetricsF(body_font).horizontalAdvance(self._body)
        if self._expanded:
            width = int(min(440.0, max(300.0, max(title_width, body_width) + 64.0)))
            return QSize(width, 70)
        width = int(max(150.0, min(400.0, title_width + 62.0)))
        return QSize(width, 44)

    def _apply_size(self, animate):
        target = self._target_size()
        current = self.geometry()
        goal = QRect(current.center().x() - target.width() // 2, current.top(),
                     target.width(), target.height())
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            area = screen.availableGeometry()
            left = max(area.left(), min(area.right() - target.width() + 1, goal.left()))
            goal.moveLeft(left)
        self._size_anim.stop()
        if not animate or not self.isVisible():
            self.setGeometry(goal)
            return
        self._size_anim.setStartValue(current)
        self._size_anim.setEndValue(goal)
        self._size_anim.start()

    def _reposition(self):
        target = self._target_size()
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.resize(target)
        self.move(area.center().x() - self.width() // 2, area.top() + 16)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._dismiss()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._expanded = not self._expanded
            self._shown_at = time.monotonic()
            self._apply_size(True)
            self._hide_timer.start(int(self._duration * 1000))
            self.update()

    def _dismiss(self):
        self._hide_timer.stop()
        if self._dismissing or not self.isVisible():
            return
        self._dismissing = True
        self._fade.stop()
        self._fade.setDuration(180)
        self._fade.setStartValue(max(0.0, self.windowOpacity()))
        self._fade.setEndValue(0.0)
        self._fade.start()

    def paintEvent(self, event):
        width = self.width()
        height = self.height()
        if width < 20 or height < 20:
            return
        dark = _theme_dark_widget(self)
        pal = flat_palette(dark)
        colors = _state_colors(dark)
        tone = self._tone_color(colors)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(0.5, 0.5, width - 1.0, height - 1.0)
        paint_flat_card(painter, rect, height / 2.0, pal)
        expand = max(0.0, min(1.0, (height - 44.0) / 26.0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tone)
        painter.drawEllipse(QPointF(18.0, height / 2.0 + (22.0 - height / 2.0) * expand), 4.0, 4.0)
        title_font = _ui_font(13, True)
        self._text(painter, QRectF(30.0, 8.0 * expand, width - 44.0,
                                   height * (1.0 - expand) + 18.0 * expand),
                   title_font, pal["ink"], self._title)
        if expand > 0.55:
            painter.save()
            painter.setOpacity(min(1.0, (expand - 0.55) / 0.45))
            self._text(painter, QRectF(30.0, 28.0, width - 44.0, 34.0),
                       _ui_font(11), pal["dim"], self._body)
            painter.restore()
        remain = max(0.0, 1.0 - (time.monotonic() - self._shown_at) / max(0.1, self._duration))
        if self.isVisible() and remain > 0.0:
            line = QColor(tone)
            line.setAlpha(90 if self._expanded else 60)
            line_width = max(0.0, (width - 36.0) * remain)
            if line_width > 1.0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(line)
                painter.drawRoundedRect(QRectF(18.0, height - 4.0, line_width, 2.0), 1.0, 1.0)
        painter.end()

    def _text(self, painter, rect, font, color, text, align=None):
        painter.setFont(font)
        painter.setPen(QPen(color))
        flags = int(align if align is not None else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        metrics = QFontMetricsF(font)
        value = metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, rect.width())
        painter.drawText(rect, flags, value)


class ZxRemoteNotice(QWidget):
    closed = pyqtSignal()

    def __init__(self):
        super().__init__(None)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.theme_mode = "system"
        self._title = ""
        self._body = ""
        self._sender = ""
        self._duration = 8.0
        self._shown_at = 0.0
        self._dismissing = False
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(200)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.finished.connect(self._on_fade)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._tick = QTimer(self)
        self._tick.setInterval(100)
        self._tick.timeout.connect(self.update)
        self.resize(420, 120)

    def present(self, title, body, sender, duration=8.0):
        self._title = str(title or "")
        self._body = str(body or "")
        self._sender = str(sender or "")
        try:
            value = float(duration)
        except Exception:
            value = 8.0
        self._duration = min(30.0, max(3.0, value))
        self._dismissing = False
        self._fade.stop()
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool |
                 Qt.WindowType.WindowDoesNotAcceptFocus |
                 Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlags(flags)
        self._apply_geometry()
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self.setWindowOpacity(0.0)
        self._fade.setDuration(180)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.start()
        self._shown_at = time.monotonic()
        self._timer.start(int(self._duration * 1000))
        self._tick.start()
        self.update()

    def _body_height(self, width):
        if not self._body:
            return 0.0
        metrics = QFontMetricsF(_ui_font(11))
        rect = metrics.boundingRect(QRectF(0.0, 0.0, float(width), 10000.0),
                                    int(Qt.TextFlag.TextWordWrap), self._body)
        return float(max(16.0, rect.height()))

    def _apply_geometry(self):
        width = 420
        body_height = self._body_height(width - 40)
        height = int(14 + 18 + 6 + 22 + (4 + body_height if body_height else 0) + 8 + 14 + 12)
        height = max(86, height)
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(width, height)
            return
        area = screen.availableGeometry()
        self.resize(width, height)
        self.move(area.center().x() - width // 2, area.top() + 18)

    def _on_fade(self):
        if self._dismissing:
            self._dismissing = False
            self.hide()
            self.closed.emit()

    def dismiss(self):
        self._timer.stop()
        self._tick.stop()
        if self._dismissing or not self.isVisible():
            return
        self._dismissing = True
        self._fade.stop()
        self._fade.setDuration(180)
        self._fade.setStartValue(max(0.0, self.windowOpacity()))
        self._fade.setEndValue(0.0)
        self._fade.start()

    def dismiss_now(self):
        self._timer.stop()
        self._tick.stop()
        self._fade.stop()
        self._dismissing = False
        self.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dismiss()
            return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        width = float(self.width())
        height = float(self.height())
        if width < 40.0 or height < 30.0:
            return
        dark = _theme_dark_widget(self)
        pal = flat_palette(dark)
        colors = _state_colors(dark)
        tone = colors["accent"]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        rect = QRectF(0.5, 0.5, width - 1.0, height - 1.0)
        paint_flat_card(painter, rect, 12.0, pal)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tone)
        painter.drawRoundedRect(QRectF(0.0, 14.0, 4.0, height - 28.0), 2.0, 2.0)
        badge = "教师通知"
        badge_font = _ui_font(9, True)
        badge_width = QFontMetricsF(badge_font).horizontalAdvance(badge) + 14.0
        badge_color = QColor(tone)
        badge_color.setAlpha(38)
        painter.setBrush(badge_color)
        painter.drawRoundedRect(QRectF(20.0, 14.0, badge_width, 18.0), 9.0, 9.0)
        painter.setFont(badge_font)
        painter.setPen(QPen(tone))
        painter.drawText(QRectF(20.0, 14.0, badge_width, 18.0),
                         int(Qt.AlignmentFlag.AlignCenter), badge)
        title_font = _ui_font(13, True)
        painter.setFont(title_font)
        painter.setPen(QPen(pal["ink"]))
        title_rect = QRectF(20.0, 38.0, width - 40.0, 22.0)
        painter.drawText(title_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         _elide(title_font, self._title or "通知", title_rect.width()))
        body_height = self._body_height(width - 40)
        if body_height > 0.0:
            body_rect = QRectF(20.0, 64.0, width - 40.0, body_height)
            painter.setFont(_ui_font(11))
            painter.setPen(QPen(pal["dim"]))
            painter.drawText(body_rect, int(Qt.TextFlag.TextWordWrap), self._body)
        foot_font = _ui_font(10)
        foot = "来自 %s · 点击关闭" % (self._sender or "控制端")
        painter.setFont(foot_font)
        painter.setPen(QPen(pal["dim"]))
        painter.drawText(QRectF(20.0, height - 26.0, width - 40.0, 16.0),
                         int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                         _elide(foot_font, foot, width - 40.0))
        remain = max(0.0, 1.0 - (time.monotonic() - self._shown_at) / max(0.1, self._duration))
        if remain > 0.0:
            line = QColor(tone)
            line.setAlpha(80)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(line)
            painter.drawRoundedRect(QRectF(12.0, height - 4.0, (width - 24.0) * remain, 2.0), 1.0, 1.0)
        painter.end()


class ZxRemoteNotifier(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._queue = []
        self._active = False
        self._window = ZxRemoteNotice()
        self._window.closed.connect(self._next)

    def show(self, title, body, sender, duration=8.0):
        self._queue.append((title, body, sender, duration))
        if not self._active:
            self._next()

    def _next(self):
        self._active = False
        if not self._queue:
            return
        self._active = True
        title, body, sender, duration = self._queue.pop(0)
        self._window.present(title, body, sender, duration)

    def close_all(self):
        self._queue = []
        self._window.dismiss_now()


class ZxPairDialog(QDialog):
    def __init__(self, device, ip, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("ZX 配对请求")
        self.setModal(True)
        self.resize(430, 280)
        self._remain = int(CONTROL_PAIR_TIMEOUT)
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self.setStyleSheet(_settings_qss(_theme_dark_widget(self)))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        title = QLabel("有设备请求配对", self)
        title.setFont(_ui_font(16, True))
        layout.addWidget(title)
        name = QLabel(str(device.get("name") or "未知设备"), self)
        name.setFont(_ui_font(13, True))
        layout.addWidget(name)
        detail = QLabel("%s · %s" % (_platform_label(device.get("platform")), ip), self)
        detail.setObjectName("zxVersion")
        detail.setFont(_ui_font(10))
        layout.addWidget(detail)
        note = QLabel("配对码校验通过。允许后，该设备可以修改本机课表并发送通知。", self)
        note.setWordWrap(True)
        note.setFont(_ui_font(11))
        layout.addWidget(note)
        self.lbl_count = QLabel("", self)
        self.lbl_count.setObjectName("zxVersion")
        self.lbl_count.setFont(_ui_font(10))
        layout.addWidget(self.lbl_count)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_reject = QPushButton("拒绝", self)
        btn_reject.clicked.connect(self.reject)
        row.addWidget(btn_reject)
        btn_allow = QPushButton("允许", self)
        btn_allow.setObjectName("primary")
        btn_allow.clicked.connect(self.accept)
        row.addWidget(btn_allow)
        layout.addLayout(row)
        self._tick()
        self._timer.start()

    def _tick(self):
        self.lbl_count.setText("%d 秒后自动拒绝" % max(0, self._remain))
        if self._remain <= 0:
            self._timer.stop()
            self.reject()
            return
        self._remain -= 1

    def accept(self):
        self._timer.stop()
        super().accept()

    def reject(self):
        self._timer.stop()
        super().reject()


class ZxRemoteServer(QObject):
    pair_requested = pyqtSignal(dict, str, str)
    pair_resolved = pyqtSignal(bool, str)
    devices_changed = pyqtSignal()
    schedule_changed = pyqtSignal()
    notice = pyqtSignal(str, str, str, float)

    def __init__(self, store, state_getter, state_applier, parent=None):
        super().__init__(parent)
        self.store = store
        self._state_getter = state_getter
        self._state_applier = state_applier
        self.server = None
        self.udp = None
        self.port = 0
        self._conns = {}
        self._pending = {}
        self._fails = {}
        self._sent = {}
        self._code = ""
        self._code_expire = 0.0

    def config(self):
        cfg = self.store.data.get("control")
        if not isinstance(cfg, dict):
            cfg = {}
            self.store.data["control"] = cfg
        if not str(cfg.get("host_id") or ""):
            cfg["host_id"] = "%08x" % random.getrandbits(32)
        if not isinstance(cfg.get("devices"), list):
            cfg["devices"] = []
        return cfg

    def host_name(self):
        name = str(self.config().get("name") or "").strip()
        return name or "ZX"

    def host_info(self):
        return {"id": str(self.config().get("host_id") or ""), "name": self.host_name(),
                "version": VERSION, "platform": "windows"}

    def device_rows(self):
        rows = []
        for item in self.config().get("devices") or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                "id": str(item.get("id") or ""),
                "name": str(item.get("name") or "设备"),
                "platform": str(item.get("platform") or "unknown"),
                "paired_at": int(item.get("paired_at") or 0),
                "last_seen": int(item.get("last_seen") or 0),
            })
        return rows

    def start(self):
        self.stop()
        server = QTcpServer(self)
        port = 0
        for offset in range(20):
            if server.listen(QHostAddress(QHostAddress.SpecialAddress.Any), CONTROL_BASE_PORT + offset):
                port = CONTROL_BASE_PORT + offset
                break
        if not port:
            server.deleteLater()
            _log("ZX 远程控制无法监听端口")
            return False
        server.newConnection.connect(self._on_connection)
        self.server = server
        self.port = port
        udp = QUdpSocket(self)
        bound = False
        try:
            bound = udp.bind(QHostAddress(QHostAddress.SpecialAddress.Any), CONTROL_DISCOVERY_PORT,
                             QAbstractSocket.BindFlag.ShareAddress | QAbstractSocket.BindFlag.ReuseAddressHint)
        except Exception:
            bound = False
        if bound:
            udp.readyRead.connect(self._on_probe)
            self.udp = udp
        else:
            udp.deleteLater()
            _log("ZX 远程发现端口被占用")
        self.config()
        self.store.save()
        return True

    def stop(self):
        for socket in list(self._conns.keys()):
            self._close(socket, False)
        self._conns = {}
        self._pending = {}
        self._fails = {}
        self._sent = {}
        self._code = ""
        self._code_expire = 0.0
        if self.server is not None:
            try:
                self.server.close()
                self.server.deleteLater()
            except Exception:
                pass
            self.server = None
        if self.udp is not None:
            try:
                self.udp.close()
                self.udp.deleteLater()
            except Exception:
                pass
            self.udp = None
        self.port = 0

    def generate_code(self):
        self._code = "%06d" % random.randint(0, 999999)
        self._code_expire = time.time() + CONTROL_CODE_TTL
        return self._code, CONTROL_CODE_TTL

    def code_state(self):
        if not self._code:
            return "", 0.0
        remain = self._code_expire - time.time()
        if remain <= 0.0:
            self._code = ""
            self._code_expire = 0.0
            return "", 0.0
        return self._code, remain

    def remove_device(self, device_id):
        cfg = self.config()
        target = str(device_id or "")
        before = len(cfg.get("devices") or [])
        cfg["devices"] = [item for item in cfg.get("devices") or []
                          if str(item.get("id") or "") != target]
        if len(cfg["devices"]) == before:
            return False
        self.store.save()
        self._drop_device(target)
        self.devices_changed.emit()
        return True

    def _drop_device(self, device_id):
        for socket, state in list(self._conns.items()):
            if state.get("device") == device_id:
                self._close(socket)

    def _on_connection(self):
        if self.server is None:
            return
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            if socket is None:
                continue
            ip = socket.peerAddress().toString()
            if ip.startswith("::ffff:"):
                ip = ip[7:]
            self._conns[socket] = {
                "buf": b"",
                "device": "",
                "name": "",
                "ip": ip,
            }
            socket.readyRead.connect(lambda sock=socket: self._on_ready_read(sock))
            socket.disconnected.connect(lambda sock=socket: self._drop(sock))

    def _drop(self, socket):
        state = self._conns.pop(socket, None)
        if state is not None:
            for request_id, item in list(self._pending.items()):
                if item.get("sock") is socket:
                    self._pending.pop(request_id, None)
                    self.pair_resolved.emit(False, str(item["device"].get("name") or ""))
                    break
        try:
            socket.deleteLater()
        except Exception:
            pass

    def _close(self, socket, notify=True):
        self._conns.pop(socket, None)
        if notify:
            for request_id, item in list(self._pending.items()):
                if item.get("sock") is socket:
                    self._pending.pop(request_id, None)
                    self.pair_resolved.emit(False, str(item["device"].get("name") or ""))
                    break
        try:
            socket.close()
        except Exception:
            pass
        try:
            socket.deleteLater()
        except Exception:
            pass

    def _close_later(self, socket):
        QTimer.singleShot(150, lambda sock=socket: self._close(sock, False))

    def _on_ready_read(self, socket):
        state = self._conns.get(socket)
        if state is None:
            return
        try:
            state["buf"] += bytes(socket.readAll())
        except Exception:
            return
        while len(state["buf"]) >= 4:
            size = int.from_bytes(state["buf"][:4], "big")
            if size <= 0 or size > 1048576:
                self._close(socket)
                return
            if len(state["buf"]) < size + 4:
                break
            raw = state["buf"][4:4 + size]
            state["buf"] = state["buf"][4 + size:]
            try:
                message = json.loads(raw.decode("utf-8"))
            except Exception:
                continue
            if isinstance(message, dict):
                try:
                    self._handle(socket, message)
                except Exception as exc:
                    _log("ZX 远程指令处理失败: %s" % exc)

    def _send(self, socket, payload):
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            socket.write(len(data).to_bytes(4, "big") + data)
        except Exception:
            pass

    def _handle(self, socket, message):
        kind = str(message.get("type") or "")
        if kind == "pair_request":
            self._handle_pair(socket, message)
            return
        if kind == "hello":
            self._handle_hello(socket, message)
            return
        state = self._conns.get(socket)
        if state is None or not state.get("device"):
            self._send(socket, {"type": "error", "code": "auth", "message": "设备未配对"})
            self._close_later(socket)
            return
        device_id = str(state.get("device") or "")
        name = str(state.get("name") or "设备")
        if kind == "ping":
            self._send(socket, {"type": "pong", "ts": int(time.time())})
        elif kind == "notify":
            self._handle_notify(socket, device_id, name, message)
        elif kind == "schedule_get":
            self._send(socket, {"type": "schedule_state", "rev": self._rev(),
                                "state": self._state_getter()})
        elif kind == "schedule_put":
            self._handle_schedule_put(socket, message)
        elif kind == "unpair":
            self._send(socket, {"type": "unpair_ok"})
            QTimer.singleShot(120, lambda did=device_id: self.remove_device(did))
        else:
            self._send(socket, {"type": "error", "code": "unknown", "message": "未知指令"})

    def _device_from(self, raw):
        if not isinstance(raw, dict):
            return None
        device_id = str(raw.get("id") or "").strip()
        name = str(raw.get("name") or "").strip()
        if not device_id or not name:
            return None
        platform = str(raw.get("platform") or "").strip().lower() or "unknown"
        return {"id": device_id[:64], "name": name[:40], "platform": platform[:16]}

    def _locked(self, ip):
        item = self._fails.get(str(ip or ""))
        if not item:
            return False
        if float(item.get("until") or 0.0) <= time.time():
            return False
        return True

    def _fail(self, ip):
        key = str(ip or "")
        now = time.time()
        item = self._fails.get(key)
        if not item or now - float(item.get("first") or 0.0) > 120.0:
            item = {"first": now, "count": 0, "until": 0.0}
        item["count"] = int(item.get("count") or 0) + 1
        if item["count"] >= 5:
            item["until"] = now + 60.0
            item["first"] = now
            item["count"] = 0
        self._fails[key] = item

    def _handle_pair(self, socket, message):
        state = self._conns.get(socket)
        if state is None:
            return
        ip = str(state.get("ip") or "")
        if self._locked(ip):
            self._send(socket, {"type": "pair_reject", "reason": "尝试过于频繁，请稍后再试"})
            self._close_later(socket)
            return
        code, remain = self.code_state()
        if not code:
            self._send(socket, {"type": "pair_reject", "reason": "配对码已失效，请在电脑端重新生成"})
            self._close_later(socket)
            return
        supplied = str(message.get("code") or "").strip()
        if not hmac.compare_digest(supplied, code):
            self._fail(ip)
            self._send(socket, {"type": "pair_reject", "reason": "配对码错误"})
            self._close_later(socket)
            return
        device = self._device_from(message.get("device"))
        if device is None:
            self._send(socket, {"type": "pair_reject", "reason": "设备信息不完整"})
            self._close_later(socket)
            return
        request_id = "%08x" % random.getrandbits(32)
        self._pending[request_id] = {"sock": socket, "device": device, "ip": ip}
        self.pair_requested.emit(dict(device), ip, request_id)
        QTimer.singleShot(int(CONTROL_PAIR_TIMEOUT * 1000),
                          lambda rid=request_id: self.resolve_pair(rid, False))

    def resolve_pair(self, request_id, allow):
        item = self._pending.pop(str(request_id or ""), None)
        if item is None:
            return
        socket = item["sock"]
        device = item["device"]
        if socket not in self._conns:
            self.pair_resolved.emit(False, str(device.get("name") or ""))
            return
        if not allow:
            self._send(socket, {"type": "pair_reject", "reason": "电脑端拒绝了配对"})
            self.pair_resolved.emit(False, str(device.get("name") or ""))
            self._close_later(socket)
            return
        seed = "%s|%s|%.6f|%s" % (str(self.config().get("host_id") or ""),
                                  device["id"], time.time(), random.random())
        token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
        cfg = self.config()
        rows = [row for row in cfg.get("devices") or []
                if str(row.get("id") or "") != device["id"]]
        now = int(time.time())
        rows.append({"id": device["id"], "name": device["name"],
                     "platform": device["platform"], "token": token,
                     "paired_at": now, "last_seen": now})
        cfg["devices"] = rows
        self.store.save()
        state = self._conns.get(socket)
        if state is not None:
            state["device"] = device["id"]
            state["name"] = device["name"]
        self._code = ""
        self._code_expire = 0.0
        self._send(socket, {"type": "pair_ok", "token": token, "host": self.host_info(),
                            "rev": self._rev(), "state": self._state_getter()})
        self.devices_changed.emit()
        self.pair_resolved.emit(True, str(device["name"]))

    def _handle_hello(self, socket, message):
        device_id = str(message.get("device_id") or "").strip()
        token = str(message.get("token") or "").strip()
        target = None
        for row in self.config().get("devices") or []:
            if str(row.get("id") or "") != device_id:
                continue
            if hmac.compare_digest(str(row.get("token") or ""), token):
                target = row
            break
        if target is None:
            self._send(socket, {"type": "hello_fail", "reason": "配对已失效，请重新配对"})
            self._close_later(socket)
            return
        state = self._conns.get(socket)
        if state is None:
            return
        state["device"] = device_id
        state["name"] = str(target.get("name") or "设备")
        target["last_seen"] = int(time.time())
        self._send(socket, {"type": "hello_ok", "host": self.host_info(), "rev": self._rev(),
                            "state": self._state_getter()})

    def _handle_notify(self, socket, device_id, name, message):
        now = time.time()
        stamps = self._sent.setdefault(device_id, [])
        stamps[:] = [value for value in stamps if now - value < 60.0]
        if len(stamps) >= 20:
            self._send(socket, {"type": "error", "code": "rate", "message": "发送过于频繁"})
            return
        title = str(message.get("title") or "").strip()[:60]
        body = str(message.get("body") or "").strip()[:500]
        if not title and not body:
            self._send(socket, {"type": "error", "code": "empty", "message": "通知内容为空"})
            return
        try:
            duration = float(message.get("duration") or 8.0)
        except Exception:
            duration = 8.0
        duration = min(30.0, max(3.0, duration))
        stamps.append(now)
        self.notice.emit(title or "教师通知", body, name, duration)
        self._send(socket, {"type": "notify_ok", "id": "%08x" % random.getrandbits(32)})

    def _handle_schedule_put(self, socket, message):
        base_rev = str(message.get("base_rev") or "")
        force = bool(message.get("force"))
        try:
            ok, payload = self._state_applier(message.get("state"), base_rev, force)
        except Exception as exc:
            self._send(socket, {"type": "error", "code": "schedule", "message": str(exc)})
            return
        if ok:
            self._send(socket, {"type": "schedule_saved", "rev": str(payload)})
            self.schedule_changed.emit()
            self.broadcast_schedule_changed(socket)
            return
        info = payload if isinstance(payload, dict) else {}
        self._send(socket, {"type": "schedule_conflict", "rev": str(info.get("rev") or ""),
                            "state": info.get("state") or {},
                            "message": str(info.get("message") or "课表已被修改")})

    def _rev(self):
        return _state_rev(self._state_getter())

    def broadcast_schedule_changed(self, exclude=None):
        rev = self._rev()
        for socket, state in list(self._conns.items()):
            if socket is exclude:
                continue
            if state.get("device"):
                self._send(socket, {"type": "schedule_changed", "rev": rev})

    def _on_probe(self):
        if self.udp is None:
            return
        while self.udp.hasPendingDatagrams():
            try:
                datagram = self.udp.receiveDatagram()
                payload = json.loads(bytes(datagram.data()).decode("utf-8"))
            except Exception:
                continue
            if not isinstance(payload, dict) or payload.get("zx_remote") != 1:
                continue
            if not payload.get("probe"):
                continue
            reply = {"zx_remote": 1, "host": self.host_info(), "port": int(self.port),
                     "devices": len(self.device_rows())}
            try:
                data = QByteArray(json.dumps(reply, ensure_ascii=False).encode("utf-8"))
                self.udp.writeDatagram(data, datagram.senderAddress(), datagram.senderPort())
            except Exception:
                pass


def _settings_qss(dark):
    pal = flat_palette(dark)
    colors = _theme_colors_of(dark)
    accent = QColor(colors.get("accent") or "#FBBF24")
    hover = QColor(colors.get("hover_accent") or accent)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    suffix = "dark" if dark else "light"
    caret_up = os.path.join(root, "data", "caret2_up_%s.png" % suffix).replace("\\", "/")
    caret_down = os.path.join(root, "data", "caret2_down_%s.png" % suffix).replace("\\", "/")
    values = {
        "text": colors.get("text_color") or pal["ink"].name(),
        "dim": colors.get("secondary_text") or _css_rgba(pal["dim"]),
        "line": colors.get("border_color") or _css_rgba(pal["line"]),
        "input": colors.get("input_bg") or ("#232634" if dark else "#FFFFFF"),
        "panel": colors.get("panel_bg") or ("#1A1D27" if dark else "#F3F4F6"),
        "deep": colors.get("dark_bg") or ("#12141C" if dark else "#FFFFFF"),
        "alternate": colors.get("alternate_bg") or colors.get("panel_bg") or ("#1A1D27" if dark else "#EEF0F4"),
        "accent": accent.name(),
        "accent_text": colors.get("btn_text") or ("#12141C" if dark else "#FFFFFF"),
        "hover": hover.name(),
        "danger": colors.get("danger") or "#F43F5E",
        "caret_up": caret_up,
        "caret_down": caret_down,
    }
    return """
QWidget{font-family:'Microsoft YaHei','Segoe UI';font-size:13px;color:%(text)s;background:transparent;}
QWidget#zxRoot{background:%(deep)s;}
QDialog{background:%(deep)s;color:%(text)s;}
QLabel{color:%(text)s;background:transparent;}
QLabel#zxVersion{color:%(dim)s;}
QLabel#zxRemoteCode{color:%(accent)s;}
QGroupBox{font-weight:bold;font-size:11px;color:%(dim)s;border:1px solid %(line)s;border-radius:8px;margin-top:10px;padding-top:10px;}
QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px;color:%(dim)s;}
QPushButton{background:transparent;color:%(text)s;border:1px solid %(line)s;border-radius:6px;padding:5px 12px;}
QPushButton:hover{border-color:%(accent)s;color:%(accent)s;}
QPushButton:pressed{background:%(alternate)s;color:%(accent)s;}
QPushButton:disabled{color:%(dim)s;border-color:%(line)s;}
QPushButton#primary{background:%(accent)s;color:%(accent_text)s;border:1px solid %(accent)s;font-weight:bold;}
QPushButton#primary:hover{background:%(hover)s;border-color:%(hover)s;color:%(accent_text)s;}
QPushButton#danger{background:transparent;color:%(danger)s;border:1px solid %(danger)s;}
QLineEdit,QSpinBox,QComboBox,QDateEdit,QTimeEdit{background:%(input)s;border:1px solid %(line)s;border-radius:5px;padding:4px 8px;color:%(text)s;selection-background-color:%(accent)s;}
QLineEdit:focus,QSpinBox:focus,QComboBox:focus,QDateEdit:focus,QTimeEdit:focus{border-color:%(accent)s;}
QComboBox,QDateEdit,QTimeEdit{padding-right:24px;}
QSpinBox{padding-right:24px;}
QSpinBox::up-button,QTimeEdit::up-button,QDateEdit::up-button{subcontrol-origin:border;subcontrol-position:top right;width:18px;height:13px;border:none;border-left:1px solid %(line)s;border-top-right-radius:5px;background:transparent;}
QSpinBox::down-button,QTimeEdit::down-button,QDateEdit::down-button{subcontrol-origin:border;subcontrol-position:bottom right;width:18px;height:13px;border:none;border-left:1px solid %(line)s;border-bottom-right-radius:5px;background:transparent;}
QSpinBox::up-button:hover,QTimeEdit::up-button:hover,QDateEdit::up-button:hover,QSpinBox::down-button:hover,QTimeEdit::down-button:hover,QDateEdit::down-button:hover{background:%(alternate)s;}
QSpinBox::up-arrow,QTimeEdit::up-arrow,QDateEdit::up-arrow{image:url(%(caret_up)s);width:9px;height:9px;}
QSpinBox::down-arrow,QTimeEdit::down-arrow,QDateEdit::down-arrow{image:url(%(caret_down)s);width:9px;height:9px;}
QComboBox::drop-down{border:none;width:18px;}
QComboBox QAbstractItemView{background:%(panel)s;border:1px solid %(line)s;color:%(text)s;selection-background-color:%(accent)s;selection-color:%(accent_text)s;}
QListWidget{background:%(panel)s;border:1px solid %(line)s;border-radius:8px;color:%(text)s;outline:none;}
QListWidget::item{padding:8px 10px;border-radius:5px;margin:2px 4px;}
QListWidget::item:hover{background:%(alternate)s;color:%(text)s;}
QListWidget::item:selected{background:%(alternate)s;color:%(text)s;border-left:3px solid %(accent)s;}
QTabWidget::pane{border:1px solid %(line)s;border-radius:8px;top:-1px;}
QTabBar::tab{background:transparent;color:%(dim)s;padding:6px 16px;margin-right:4px;border-radius:6px;border:1px solid transparent;}
QTabBar::tab:selected{background:%(accent)s;color:%(accent_text)s;font-weight:bold;}
QTabBar::tab:hover:!selected{color:%(text)s;background:%(panel)s;}
QCheckBox{color:%(text)s;spacing:6px;}
QCheckBox::indicator{width:16px;height:16px;border:1px solid %(line)s;border-radius:4px;background:%(input)s;}
QCheckBox::indicator:hover{border-color:%(accent)s;}
QCheckBox::indicator:checked{background:%(accent)s;border-color:%(accent)s;}
QMenu{background:%(panel)s;color:%(text)s;border:1px solid %(line)s;padding:4px;}
QMenu::item{padding:6px 22px 6px 14px;border-radius:4px;}
QMenu::item:selected{background:%(alternate)s;color:%(text)s;}
QMenu::separator{height:1px;background:%(line)s;margin:4px 8px;}
QToolTip{background:%(panel)s;color:%(text)s;border:1px solid %(line)s;padding:4px;border-radius:4px;}
QScrollBar:vertical{background:transparent;width:8px;margin:0;}
QScrollBar::handle:vertical{background:%(line)s;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QScrollBar:horizontal{background:%(panel)s;height:8px;margin:0;}
QScrollBar::handle:horizontal{background:%(line)s;border-radius:4px;min-width:30px;}
QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{width:0px;}
QCalendarWidget QWidget{alternate-background-color:%(alternate)s;}
QCalendarWidget QAbstractItemView{background:%(panel)s;color:%(text)s;selection-background-color:%(accent)s;selection-color:%(accent_text)s;}
""" % values


def _styled_box(parent, icon, text):
    box = QMessageBox(parent)
    box.setWindowTitle("ZX")
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    box.setStyleSheet(_settings_qss(_theme_dark_widget(parent)))
    box.exec()


def _ask_confirm(parent, text):
    box = QMessageBox(parent)
    box.setWindowTitle("ZX")
    box.setText(text)
    box.setIcon(QMessageBox.Icon.Question)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.setStyleSheet(_settings_qss(_theme_dark_widget(parent)))
    return box.exec() == QMessageBox.StandardButton.Yes


def _ask_text(parent, title, label, default=""):
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setTextValue(default)
    dialog.setStyleSheet(_settings_qss(_theme_dark_widget(parent)))
    ok = dialog.exec() == QDialog.DialogCode.Accepted
    return dialog.textValue(), ok


class ZxPeriodsDialog(QDialog):
    def __init__(self, parent, periods, index=0):
        super().__init__(parent)
        self.theme_mode = "system"
        self.setWindowTitle("节次时间")
        self.resize(430, 520)
        self.setStyleSheet(_settings_qss(_theme_dark_widget(self)))
        self._periods = [[int(item[0]), int(item[1])] for item in periods]
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.list = QListWidget(self)
        layout.addWidget(self.list, 1)
        form = QHBoxLayout()
        form.setSpacing(8)
        self.time_start = QTimeEdit(self)
        self.time_start.setDisplayFormat("HH:mm")
        self.time_end = QTimeEdit(self)
        self.time_end.setDisplayFormat("HH:mm")
        form.addWidget(QLabel("开始", self))
        form.addWidget(self.time_start, 1)
        form.addWidget(QLabel("结束", self))
        form.addWidget(self.time_end, 1)
        btn_apply = QPushButton("写入所选节次", self)
        btn_apply.clicked.connect(self._apply_time)
        form.addWidget(btn_apply)
        layout.addLayout(form)
        row = QHBoxLayout()
        row.setSpacing(8)
        btn_add = QPushButton("添加", self)
        btn_add.clicked.connect(self._add)
        btn_del = QPushButton("删除", self)
        btn_del.clicked.connect(self._remove)
        btn_up = QPushButton("上移", self)
        btn_up.clicked.connect(lambda: self._move(-1))
        btn_down = QPushButton("下移", self)
        btn_down.clicked.connect(lambda: self._move(1))
        row.addWidget(btn_add)
        row.addWidget(btn_del)
        row.addWidget(btn_up)
        row.addWidget(btn_down)
        row.addStretch(1)
        layout.addLayout(row)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel, self)
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("保存")
        btn_ok.setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.list.currentRowChanged.connect(self._on_row)
        self._fill()
        if self._periods:
            self.list.setCurrentRow(max(0, min(len(self._periods) - 1, int(index or 0))))

    def showEvent(self, event):
        super().showEvent(event)
        _animate_dialog_show(self)

    def _fill(self):
        row = self.list.currentRow()
        self.list.clear()
        for index, item in enumerate(self._periods):
            self.list.addItem("%d.  %s - %s" % (index + 1, _fmt_clock(item[0]), _fmt_clock(item[1])))
        if self._periods:
            self.list.setCurrentRow(max(0, min(len(self._periods) - 1, row)))

    def _on_row(self, row):
        if row < 0 or row >= len(self._periods):
            return
        start, end = self._periods[row]
        self.time_start.setTime(QTime(start // 60, start % 60))
        self.time_end.setTime(QTime(end // 60, end % 60))

    def _apply_time(self):
        row = self.list.currentRow()
        if row < 0 or row >= len(self._periods):
            return
        start = self.time_start.time().hour() * 60 + self.time_start.time().minute()
        end = self.time_end.time().hour() * 60 + self.time_end.time().minute()
        if end <= start:
            return
        self._periods[row] = [start, end]
        self._fill()
        self.list.setCurrentRow(row)

    def _add(self):
        if self._periods:
            start = min(1438, self._periods[-1][1] + 10)
        else:
            start = 480
        self._periods.append([start, min(1439, start + 45)])
        self._fill()
        self.list.setCurrentRow(len(self._periods) - 1)

    def _remove(self):
        row = self.list.currentRow()
        if row < 0 or len(self._periods) <= 1:
            return
        self._periods.pop(row)
        self._fill()
        self.list.setCurrentRow(min(row, len(self._periods) - 1))

    def _move(self, delta):
        row = self.list.currentRow()
        target = row + delta
        if row < 0 or target < 0 or target >= len(self._periods):
            return
        self._periods[row], self._periods[target] = self._periods[target], self._periods[row]
        self._fill()
        self.list.setCurrentRow(target)

    def result_periods(self):
        return [list(item) for item in self._periods]


def _period_for_minute(periods, minute):
    best_index = 0
    best_delta = None
    for index, item in enumerate(periods):
        start, end = int(item[0]), int(item[1])
        if start <= minute < end:
            return index
        delta = abs(start - minute)
        if best_delta is None or delta < best_delta:
            best_index = index
            best_delta = delta
    return best_index


class ZxLessonDialog(QDialog):
    def __init__(self, parent, entry, periods, day, period=0):
        super().__init__(parent)
        self.theme_mode = "system"
        self.setWindowTitle("课程")
        self.setMinimumWidth(430)
        self.setStyleSheet(_settings_qss(_theme_dark_widget(self)))
        self._entry = dict(entry) if isinstance(entry, dict) else {}
        self._periods = [tuple(item) for item in periods] or [tuple(item) for item in DEFAULT_PERIODS]
        self._kind = "activity" if self._entry.get("kind") == "activity" else "lesson"
        self._loading = True
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.form = QFormLayout()
        self.form.setSpacing(10)
        self.cmb_kind = QComboBox(self)
        self.cmb_kind.addItem("课程", "lesson")
        self.cmb_kind.addItem("活动", "activity")
        self.cmb_kind.setCurrentIndex(1 if self._kind == "activity" else 0)
        self.cmb_kind.currentIndexChanged.connect(self._on_kind_changed)
        self.form.addRow("类型", self.cmb_kind)
        self.edit_name = QLineEdit(self)
        self.edit_name.setText(str(self._entry.get("name") or ""))
        self.edit_name.textChanged.connect(self._update_preview)
        self.form.addRow("名称", self.edit_name)
        self.edit_room = QLineEdit(self)
        self.edit_room.setText(str(self._entry.get("room") or ""))
        self.edit_room.textChanged.connect(self._update_preview)
        self.form.addRow("地点", self.edit_room)
        self.cmb_day = QComboBox(self)
        for index, name in enumerate(WEEKDAY_NAMES):
            self.cmb_day.addItem(name, index + 1)
        self.cmb_day.setCurrentIndex(max(0, min(6, int(self._entry.get("day", day) or day) - 1)))
        self.cmb_day.currentIndexChanged.connect(self._update_preview)
        self.form.addRow("星期", self.cmb_day)
        self.cmb_start = QComboBox(self)
        for index in range(len(self._periods)):
            start, _end = self._periods[index]
            self.cmb_start.addItem("第 %d 节  %s 开始" % (index + 1, _fmt_clock(start)), index)
        start_index = int(period if entry is None else self._entry.get("period", period) or 0)
        self.cmb_start.setCurrentIndex(max(0, min(len(self._periods) - 1, start_index)))
        self.cmb_start.currentIndexChanged.connect(self._on_start_changed)
        self.form.addRow("起始节次", self.cmb_start)
        self.spin_span = QSpinBox(self)
        self.spin_span.setRange(1, max(1, min(6, len(self._periods))))
        self.spin_span.setSuffix(" 节")
        self.spin_span.valueChanged.connect(self._on_span_changed)
        self.form.addRow("连续节数", self.spin_span)
        self.lbl_time = QLabel("上课时间", self)
        time_row = QHBoxLayout()
        time_row.setSpacing(6)
        self.time_start = QTimeEdit(self)
        self.time_start.setDisplayFormat("HH:mm")
        self.time_start.setFixedWidth(118)
        self.time_start.timeChanged.connect(self._update_preview)
        self.time_end = QTimeEdit(self)
        self.time_end.setDisplayFormat("HH:mm")
        self.time_end.setFixedWidth(118)
        self.time_end.timeChanged.connect(self._update_preview)
        time_row.addWidget(self.time_start)
        time_row.addWidget(QLabel("至", self))
        time_row.addWidget(self.time_end)
        time_row.addStretch(1)
        self.form.addRow(self.lbl_time, time_row)
        self.cmb_weeks = QComboBox(self)
        for key in ("all", "odd", "even"):
            self.cmb_weeks.addItem(WEEK_LABELS[key], key)
        self.cmb_weeks.setCurrentIndex(max(0, self.cmb_weeks.findData(str(self._entry.get("weeks") or "all"))))
        self.cmb_weeks.currentIndexChanged.connect(self._update_preview)
        self.form.addRow("周次", self.cmb_weeks)
        layout.addLayout(self.form)
        self.lbl_preview = QLabel("", self)
        self.lbl_preview.setObjectName("zxVersion")
        layout.addWidget(self.lbl_preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel, self)
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_ok.setText("保存")
        btn_ok.setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._loading = False
        self._apply_kind()
        self._fill_times()
        try:
            custom_start = self._entry.get("start")
            custom_end = self._entry.get("end")
            if custom_start is not None and custom_end is not None:
                self.time_start.setTime(QTime(int(custom_start) // 60, int(custom_start) % 60))
                self.time_end.setTime(QTime(int(custom_end) // 60, int(custom_end) % 60))
        except Exception:
            pass
        self._update_preview()
        self.edit_name.setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        _animate_dialog_show(self)

    def _on_kind_changed(self, _index):
        self._kind = "activity" if self.cmb_kind.currentData() == "activity" else "lesson"
        self._apply_kind()
        if not self._loading:
            self._fill_times()
        self._update_preview()

    def _apply_kind(self):
        activity = self._kind == "activity"
        for widget in (self.cmb_start, self.spin_span):
            widget.setVisible(not activity)
            label = self.form.labelForField(widget)
            if label is not None:
                label.setVisible(not activity)
        self.lbl_time.setText("活动时间" if activity else "上课时间")
        self.setWindowTitle("活动" if activity else "课程")
        self.edit_name.setPlaceholderText("例如：升旗仪式、大课间" if activity else "例如：数学")
        self.edit_room.setPlaceholderText("例如：操场" if activity else "例如：高一(1)班")

    def _on_start_changed(self, index):
        span_max = max(1, len(self._periods) - max(0, int(index)))
        self.spin_span.setMaximum(min(6, span_max))
        if self.spin_span.value() > self.spin_span.maximum():
            self.spin_span.setValue(self.spin_span.maximum())
        if not self._loading:
            self._fill_times()
        self._update_preview()

    def _on_span_changed(self, _value):
        if not self._loading:
            self._fill_times()
        self._update_preview()

    def _fill_times(self):
        start_index = max(0, int(self.cmb_start.currentData() or 0))
        span = max(1, min(int(self.spin_span.value()), len(self._periods) - start_index))
        end_index = min(len(self._periods) - 1, start_index + span - 1)
        self.time_start.setTime(QTime(int(self._periods[start_index][0]) // 60,
                                      int(self._periods[start_index][0]) % 60))
        self.time_end.setTime(QTime(int(self._periods[end_index][1]) // 60,
                                    int(self._periods[end_index][1]) % 60))

    def _update_preview(self):
        day_name = WEEKDAY_NAMES[max(0, min(6, int(self.cmb_day.currentData() or 1) - 1))]
        weeks = WEEK_LABELS.get(str(self.cmb_weeks.currentData() or "all"), "每周")
        if self._kind == "activity":
            name = self.edit_name.text().strip() or "未命名活动"
            clock = "%s - %s" % (self.time_start.time().toString("HH:mm"),
                                 self.time_end.time().toString("HH:mm"))
            self.lbl_preview.setText("%s · %s · %s · %s" % (day_name, clock, weeks, name))
            return
        start_index = max(0, int(self.cmb_start.currentData() or 0))
        span = max(1, min(int(self.spin_span.value()), len(self._periods) - start_index))
        end_index = min(len(self._periods) - 1, start_index + span - 1)
        clock = "%s - %s" % (self.time_start.time().toString("HH:mm"),
                             self.time_end.time().toString("HH:mm"))
        if span <= 1:
            span_text = "第 %d 节" % (start_index + 1)
        else:
            span_text = "第 %d - %d 节" % (start_index + 1, end_index + 1)
        name = self.edit_name.text().strip() or "未命名课程"
        self.lbl_preview.setText("%s · %s · %s · %s · %s" % (day_name, span_text, clock, weeks, name))

    def _accept(self):
        if not self.edit_name.text().strip():
            self.edit_name.setFocus()
            return
        if self._kind == "activity" and self._time_minutes(self.time_end) <= self._time_minutes(self.time_start):
            QMessageBox.warning(self, "时间不正确", "活动结束时间需要晚于开始时间")
            return
        self.accept()

    @staticmethod
    def _time_minutes(widget):
        value = widget.time()
        return value.hour() * 60 + value.minute()

    def result_entries(self):
        name = self.edit_name.text().strip() or "未命名"
        room = self.edit_room.text().strip()
        day = int(self.cmb_day.currentData() or 1)
        weeks = str(self.cmb_weeks.currentData() or "all")
        if self._kind == "activity":
            start_at = self._time_minutes(self.time_start)
            end_at = self._time_minutes(self.time_end)
            return [{
                "day": day,
                "period": _period_for_minute(self._periods, start_at),
                "name": name,
                "room": room,
                "weeks": weeks,
                "kind": "activity",
                "start": start_at,
                "end": end_at,
            }]
        start_index = max(0, int(self.cmb_start.currentData() or 0))
        span = max(1, min(int(self.spin_span.value()), len(self._periods) - start_index))
        rows = []
        for offset in range(span):
            rows.append({
                "day": day,
                "period": start_index + offset,
                "name": name,
                "room": room,
                "weeks": weeks,
            })
        if span == 1:
            start_at = self._time_minutes(self.time_start)
            end_at = self._time_minutes(self.time_end)
            if end_at > start_at and (start_at, end_at) != tuple(int(item) for item in self._periods[start_index]):
                rows[0]["start"] = start_at
                rows[0]["end"] = end_at
        return rows


class ZxWeekGrid(QWidget):
    cell_activated = pyqtSignal(int, int)
    cell_menu = pyqtSignal(int, int, QPoint)
    periods_requested = pyqtSignal()
    period_clicked = pyqtSignal(int)
    entry_dropped = pyqtSignal(int, int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_mode = "system"
        self._entries = []
        self._periods = [tuple(item) for item in DEFAULT_PERIODS]
        self._hover = None
        self._hover_alpha = 0.0
        self._reveal = 1.0
        self._header = 24.0
        self._gutter = 74.0
        self._press_cell = None
        self._press_pos = None
        self._drag_entry = None
        self._dragging = False
        self._drag_pos = None
        self._drag_target = None
        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(150)
        self._hover_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_hover_value)
        self._reveal_anim = QVariantAnimation(self)
        self._reveal_anim.setDuration(300)
        self._reveal_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._reveal_anim.valueChanged.connect(self._on_reveal_value)
        self.setMouseTracking(True)
        self.setMinimumHeight(330)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _on_hover_value(self, value):
        self._hover_alpha = float(value)
        self.update()

    def _on_reveal_value(self, value):
        self._reveal = float(value)
        self.update()

    def set_theme_mode(self, mode):
        value = str(mode or "").lower()
        self.theme_mode = value if value in ("dark", "light") else "system"
        self.update()

    def set_data(self, entries, periods):
        self._entries = [dict(item) for item in entries
                         if isinstance(item, dict) and str(item.get("kind") or "lesson") != "activity"]
        self._periods = [tuple(item) for item in periods] or [tuple(item) for item in DEFAULT_PERIODS]
        self._reveal = 0.0
        self._reveal_anim.stop()
        self._reveal_anim.setStartValue(0.0)
        self._reveal_anim.setEndValue(1.0)
        self._reveal_anim.start()
        self.update()

    def _period_at_y(self, y):
        _width, _height, header, _gutter, row_h, _col_w = self._metrics()
        if y < header:
            return None
        index = int((y - header) // row_h)
        if index < 0 or index >= len(self._periods):
            return None
        return index

    def _metrics(self):
        width = float(self.width())
        height = float(self.height())
        rows = max(1, len(self._periods))
        header = self._header
        gutter = self._gutter
        row_h = max(12.0, (height - header) / rows)
        col_w = max(12.0, (width - gutter) / 7.0)
        return width, height, header, gutter, row_h, col_w

    def _cell_at(self, point):
        _width, _height, header, gutter, row_h, col_w = self._metrics()
        if point.y() < header or point.x() < gutter:
            return None
        day = int((point.x() - gutter) // col_w) + 1
        period = int((point.y() - header) // row_h)
        if day < 1 or day > 7 or period < 0 or period >= len(self._periods):
            return None
        return day, period

    def _entry_at(self, day, period):
        for entry in self._entries:
            if int(entry.get("day", 0) or 0) == day and int(entry.get("period", 0) or 0) == period:
                return entry
        return None

    def _set_hover(self, cell):
        if cell == self._hover:
            return
        self._hover = cell
        self._hover_alpha = 0.0
        self._hover_anim.stop()
        if cell is not None:
            self._hover_anim.setStartValue(0.0)
            self._hover_anim.setEndValue(1.0)
            self._hover_anim.start()
        self.update()

    def mouseMoveEvent(self, event):
        if self._press_cell is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if not self._dragging and self._drag_entry is not None and self._press_pos is not None:
                delta = event.position() - self._press_pos
                if abs(delta.x()) > 6 or abs(delta.y()) > 6:
                    self._dragging = True
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
            if self._dragging:
                self._drag_pos = event.position()
                self._drag_target = self._cell_at(event.position())
                self.update()
                return
        cell = self._cell_at(event.position())
        self._set_hover(cell)
        if cell is not None:
            entry = self._entry_at(cell[0], cell[1])
            if entry is None:
                self.setToolTip("%s · 第 %d 节 · 单击添加课程，按住可拖动课程" % (
                    WEEKDAY_NAMES[cell[0] - 1], cell[1] + 1))
            else:
                self.setToolTip("%s · 第 %d 节 · 单击编辑 %s，按住可拖动到其他节次" % (
                    WEEKDAY_NAMES[cell[0] - 1], cell[1] + 1, entry.get("name") or ""))
        else:
            index = self._period_at_y(event.position().y())
            if event.position().x() < self._gutter and index is not None:
                start, end = self._periods[index]
                self.setToolTip("单击调整第 %d 节时间 · %s - %s" % (
                    index + 1, _fmt_clock(start), _fmt_clock(end)))
            else:
                self.setToolTip("单击左侧节次可调整该节时间")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._set_hover(None)
        self.setToolTip("")
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            cell = self._cell_at(event.position())
            if cell is not None:
                self.cell_menu.emit(cell[0], cell[1], event.globalPos())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if event.position().x() < self._gutter:
            index = self._period_at_y(event.position().y())
            if index is not None:
                self.period_clicked.emit(index)
            return
        cell = self._cell_at(event.position())
        if cell is None:
            return
        self._press_cell = cell
        self._press_pos = event.position()
        self._drag_entry = self._entry_at(cell[0], cell[1])
        self._dragging = False
        self._drag_pos = None
        self._drag_target = None

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._dragging and self._drag_entry is not None and self._drag_target is not None:
            source_day = int(self._drag_entry.get("day", 0) or 0)
            source_period = int(self._drag_entry.get("period", 0) or 0)
            target_day, target_period = self._drag_target
            self._dragging = False
            self._press_cell = None
            self._press_pos = None
            self._drag_entry = None
            self._drag_pos = None
            self._drag_target = None
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            if (target_day, target_period) != (source_day, source_period):
                self.entry_dropped.emit(source_day, source_period, target_day, target_period)
            self.update()
            return
        cell = self._press_cell
        was_drag = self._dragging
        self._dragging = False
        self._press_cell = None
        self._press_pos = None
        self._drag_entry = None
        self._drag_pos = None
        self._drag_target = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if not was_drag and cell is not None:
            self.cell_activated.emit(cell[0], cell[1])
        self.update()

    def mouseDoubleClickEvent(self, event):
        if event.position().x() < self._gutter and event.button() == Qt.MouseButton.LeftButton:
            index = self._period_at_y(event.position().y())
            if index is not None:
                self.period_clicked.emit(index)
            return
        super().mouseDoubleClickEvent(event)

    def _text(self, painter, rect, font, color, text, align=None):
        painter.setFont(font)
        painter.setPen(QPen(color))
        flags = int(align if align is not None else (Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter))
        metrics = QFontMetricsF(font)
        value = metrics.elidedText(str(text), Qt.TextElideMode.ElideRight, max(0.0, rect.width()))
        painter.drawText(rect, flags, value)

    def paintEvent(self, event):
        width = self.width()
        height = self.height()
        if width < 80 or height < 80:
            return
        dark = _theme_dark_widget(self)
        pal = flat_palette(dark)
        colors = _theme_colors_of(dark)
        accent = QColor(colors.get("accent") or "#FBBF24")
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        _width, _height, header, gutter, row_h, col_w = self._metrics()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(pal["surface"])
        painter.drawRoundedRect(QRectF(0.5, 0.5, width - 1.0, height - 1.0), 10.0, 10.0)
        line_color = QColor(pal["line"])
        line_color.setAlpha(70)
        pen = QPen(line_color, 1.0)
        painter.setPen(pen)
        for column in range(1, 7):
            x = gutter + column * col_w
            painter.drawLine(QPointF(x, header), QPointF(x, height - 1.0))
        for row in range(1, len(self._periods)):
            y = header + row * row_h
            painter.drawLine(QPointF(gutter, y), QPointF(width - 1.0, y))
        painter.setPen(Qt.PenStyle.NoPen)
        current = _now()
        today = current.date().isoweekday()
        now_minutes = current.hour * 60 + current.minute + current.second / 60.0
        current_row = -1
        for index, item in enumerate(self._periods):
            if int(item[0]) <= now_minutes < int(item[1]):
                current_row = index
                break
        if 1 <= today <= 7 and current_row >= 0:
            band = QColor(accent)
            band.setAlpha(16)
            painter.setBrush(band)
            painter.drawRect(QRectF(gutter, header + current_row * row_h, width - gutter - 1.0, row_h))
        head_font = _ui_font(10.5, True)
        for index, name in enumerate(WEEKDAY_NAMES):
            left = gutter + index * col_w
            box = QRectF(left, 2.0, col_w, header - 4.0)
            if index + 1 == today:
                tint = QColor(accent)
                tint.setAlpha(38)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(tint)
                painter.drawRoundedRect(QRectF(left + 3.0, 3.0, col_w - 6.0, header - 7.0), 4.0, 4.0)
                self._text(painter, box, head_font, accent, name, Qt.AlignmentFlag.AlignCenter)
            else:
                self._text(painter, box, head_font, pal["dim"], name, Qt.AlignmentFlag.AlignCenter)
        for index, item in enumerate(self._periods):
            top = header + index * row_h
            index_font = _ui_font(max(8.5, min(10.5, row_h * 0.36)), True)
            self._text(painter, QRectF(3.0, top, 15.0, row_h), index_font, pal["dim"], str(index + 1),
                       Qt.AlignmentFlag.AlignCenter)
            if row_h >= 28.0:
                start_font = _num_font(max(8.6, min(10.0, row_h * 0.30)))
                end_font = _num_font(max(8.0, min(9.4, row_h * 0.28)))
                self._text(painter, QRectF(19.0, top + 1.0, gutter - 23.0, row_h * 0.5 - 1.0),
                           start_font, pal["dim"], _fmt_clock(item[0]),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._text(painter, QRectF(19.0, top + row_h * 0.5, gutter - 23.0, row_h * 0.5 - 1.0),
                           end_font, pal["dim"], _fmt_clock(item[1]),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                time_font = _num_font(max(8.0, min(9.6, row_h * 0.36)))
                self._text(painter, QRectF(18.0, top, gutter - 21.0, row_h), time_font, pal["dim"],
                           "%s-%s" % (_fmt_clock(item[0]), _fmt_clock(item[1])),
                           Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if self._hover is not None and self._hover_alpha > 0.01:
            day, period = self._hover
            left = gutter + (day - 1) * col_w
            top = header + period * row_h
            box = QRectF(left + 1.5, top + 1.5, col_w - 3.0, row_h - 3.0)
            existing = self._entry_at(day, period)
            tint = QColor(accent if existing is None else _lesson_color(existing.get("name"), dark))
            tint.setAlpha(int((30 if existing is None else 22) * self._hover_alpha))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(tint)
            painter.drawRoundedRect(box, 5.0, 5.0)
        if self._dragging and self._drag_target is not None:
            day, period = self._drag_target
            left = gutter + (day - 1) * col_w
            top = header + period * row_h
            painter.setPen(QPen(accent, 1.4, Qt.PenStyle.DashLine))
            painter.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 26))
            painter.drawRoundedRect(QRectF(left + 2.0, top + 2.0, col_w - 4.0, row_h - 4.0), 5.0, 5.0)
        painter.save()
        painter.setOpacity(max(0.0, min(1.0, self._reveal)))
        for entry in self._entries:
            day = int(entry.get("day", 0) or 0)
            period = int(entry.get("period", 0) or 0)
            if day < 1 or day > 7 or period < 0 or period >= len(self._periods):
                continue
            if self._dragging and entry is self._drag_entry:
                continue
            color = _lesson_color(entry.get("name"), dark)
            left = gutter + (day - 1) * col_w + 2.0
            top = header + period * row_h + 1.5
            lift = 0.0
            if self._hover == (day, period):
                lift = 1.0 * self._hover_alpha
            box = QRectF(left, top - lift, col_w - 4.0, row_h - 3.0)
            fill = QColor(color)
            fill.setAlpha(int((34 if dark else 26) + 14 * self._reveal))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(box, 5.0, 5.0)
            bar = QRectF(box.left(), box.top() + 1.0, 3.0, max(2.0, box.height() - 2.0))
            painter.setBrush(color)
            painter.drawRoundedRect(bar, 1.5, 1.5)
            text_color = QColor(color) if dark else QColor(color).darker(115)
            if box.height() >= 28.0:
                name_font = _ui_font(max(9.0, min(12.0, box.height() * 0.38)), True)
                sub_font = _ui_font(max(8.0, min(10.0, box.height() * 0.30)))
                self._text(painter, QRectF(box.left() + 7.0, box.top() + 1.0, box.width() - 9.0, box.height() * 0.54),
                           name_font, text_color, entry.get("name") or "未命名")
                sub = str(entry.get("room") or "")
                if entry.get("start") is not None and entry.get("end") is not None:
                    clock = "%s-%s" % (_fmt_clock(entry["start"]), _fmt_clock(entry["end"]))
                    sub = (sub + " " if sub else "") + clock
                weeks = str(entry.get("weeks") or "all")
                if weeks != "all":
                    sub = (sub + " " if sub else "") + WEEK_LABELS.get(weeks, "每周")
                self._text(painter, QRectF(box.left() + 7.0, box.top() + box.height() * 0.5,
                                           box.width() - 9.0, box.height() * 0.46),
                           sub_font, pal["dim"], sub)
            else:
                name_font = _ui_font(max(9.0, min(11.0, box.height() * 0.62)), True)
                self._text(painter, QRectF(box.left() + 7.0, box.top(), box.width() - 9.0, box.height()),
                           name_font, text_color, entry.get("name") or "未命名")
        painter.restore()
        if self._dragging and self._drag_entry is not None and self._drag_pos is not None:
            ghost_font = _ui_font(10.5, True)
            text = str(self._drag_entry.get("name") or "")
            ghost_w = QFontMetricsF(ghost_font).horizontalAdvance(text) + 24.0
            ghost = QRectF(self._drag_pos.x() + 10.0, self._drag_pos.y() + 10.0, ghost_w, 26.0)
            painter.setPen(QPen(accent, 1.0))
            fill = QColor(pal["surface"])
            fill.setAlpha(236)
            painter.setBrush(fill)
            painter.drawRoundedRect(ghost, 6.0, 6.0)
            self._text(painter, ghost.adjusted(10.0, 0.0, -8.0, 0.0), ghost_font, pal["ink"], text)
        painter.end()


class ZxSettingsPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("zxRoot")
        self.setMinimumSize(900, 640)
        self.theme_mode = "system"
        self._dark = None
        self._loading = True
        self._build()
        self._apply_theme()
        self._load()
        self._loading = False
        try:
            _service().remote_schedule_changed.connect(self._on_remote_schedule)
        except Exception:
            pass
        self._remote_timer = QTimer(self)
        self._remote_timer.setInterval(2000)
        self._remote_timer.timeout.connect(self._refresh_remote)
        self._remote_timer.start()
        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(1000)
        self._clock_timer.timeout.connect(self._refresh_clock_label)
        self._clock_timer.start()

    def set_theme_mode(self, mode):
        value = str(mode or "").lower()
        self.theme_mode = value if value in ("dark", "light") else "system"
        self._apply_theme()

    def _apply_theme(self):
        self._dark = _theme_dark_widget(self)
        self.setStyleSheet(_settings_qss(self._dark))

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(6)
        head = QHBoxLayout()
        title = QLabel("ZX 智能助手", self)
        title.setFont(_ui_font(16, True))
        head.addWidget(title)
        head.addSpacing(10)
        version = QLabel("v%s · 构建 %s" % (VERSION, BUILD_VERSION), self)
        version.setFont(_ui_font(10))
        version.setObjectName("zxVersion")
        head.addWidget(version)
        head.addStretch(1)
        layout.addLayout(head)
        tabs = QTabWidget(self)
        tabs.addTab(self._build_schedule_tab(), "课程表")
        tabs.addTab(self._build_remote_tab(), "远程")
        tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(tabs, 1)
        self.tabs = tabs

    def _on_tab_changed(self, index):
        page = self.tabs.widget(index)
        if page is None:
            return
        effect = page.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(page)
            page.setGraphicsEffect(effect)
        previous = getattr(self, "_tab_anim", None)
        if previous is not None:
            previous.stop()
            previous.deleteLater()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(200)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(0.3)
        anim.setEndValue(1.0)
        self._tab_anim = anim
        anim.start()

    def _build_schedule_tab(self):
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 6, 4, 0)
        outer.setSpacing(7)
        plan_row = QHBoxLayout()
        plan_row.setSpacing(8)
        plan_row.addWidget(QLabel("方案", page))
        self.cmb_plan = QComboBox(page)
        self.cmb_plan.setMinimumWidth(160)
        self.cmb_plan.currentTextChanged.connect(self._on_plan_changed)
        plan_row.addWidget(self.cmb_plan)
        btn_new = QPushButton("新建", page)
        btn_new.clicked.connect(self._new_plan)
        btn_rename = QPushButton("重命名", page)
        btn_rename.clicked.connect(self._rename_plan)
        btn_delete = QPushButton("删除", page)
        btn_delete.clicked.connect(self._delete_plan)
        plan_row.addWidget(btn_new)
        plan_row.addWidget(btn_rename)
        plan_row.addWidget(btn_delete)
        plan_row.addStretch(1)
        outer.addLayout(plan_row)
        week_row = QHBoxLayout()
        week_row.setSpacing(8)
        week_row.addWidget(QLabel("单双周", page))
        self.cmb_week = QComboBox(page)
        self.cmb_week.setFixedWidth(126)
        for key in ("auto", "odd", "even"):
            self.cmb_week.addItem(WEEK_MODES[key], key)
        self.cmb_week.currentIndexChanged.connect(self._on_week_mode)
        week_row.addWidget(self.cmb_week)
        week_row.addSpacing(16)
        week_row.addWidget(QLabel("开学日期", page))
        self.date_start = QDateEdit(page)
        self.date_start.setFixedWidth(142)
        self.date_start.setCalendarPopup(True)
        self.date_start.setDisplayFormat("yyyy-MM-dd")
        self.date_start.setMinimumDate(QDate(2000, 1, 1))
        self.date_start.setSpecialValueText("未设置")
        self.date_start.dateChanged.connect(self._on_semester_start)
        week_row.addWidget(self.date_start)
        week_row.addSpacing(16)
        week_row.addWidget(QLabel("提前提醒", page))
        self.spin_remind = QSpinBox(page)
        self.spin_remind.setRange(0, 30)
        self.spin_remind.setSuffix(" 分钟")
        self.spin_remind.setFixedWidth(96)
        self.spin_remind.valueChanged.connect(self._on_remind_changed)
        week_row.addWidget(self.spin_remind)
        week_row.addStretch(1)
        outer.addLayout(week_row)
        self.grid_week = ZxWeekGrid(page)
        self.grid_week.cell_activated.connect(self._on_cell)
        self.grid_week.cell_menu.connect(self._on_cell_menu)
        self.grid_week.periods_requested.connect(lambda: self._edit_periods())
        self.grid_week.period_clicked.connect(self._edit_periods)
        self.grid_week.entry_dropped.connect(self._on_entry_dropped)
        outer.addWidget(self.grid_week, 1)
        self.list_activity = QListWidget(page)
        self.list_activity.setFixedHeight(88)
        self.list_activity.itemDoubleClicked.connect(self._on_activity_double)
        self.list_activity.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_activity.customContextMenuRequested.connect(self._on_activity_menu)
        outer.addWidget(self.list_activity)
        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        btn_add = QPushButton("添加课程", page)
        btn_add.setObjectName("primary")
        btn_add.clicked.connect(lambda: self._add_lesson())
        btn_activity = QPushButton("添加活动", page)
        btn_activity.clicked.connect(lambda: self._add_activity())
        btn_periods = QPushButton("节次时间", page)
        btn_periods.clicked.connect(lambda: self._edit_periods())
        btn_clear = QPushButton("清空方案", page)
        btn_clear.clicked.connect(self._clear_plan)
        button_row.addWidget(btn_add)
        button_row.addWidget(btn_activity)
        button_row.addWidget(btn_periods)
        button_row.addWidget(btn_clear)
        button_row.addStretch(1)
        outer.addLayout(button_row)
        sync_row = QHBoxLayout()
        sync_row.setSpacing(8)
        self.chk_sync = QCheckBox("联网校时", page)
        self.chk_sync.toggled.connect(self._on_time_sync)
        sync_row.addWidget(self.chk_sync)
        self.lbl_clock = QLabel("", page)
        self.lbl_clock.setFont(_ui_font(10))
        self.lbl_clock.setObjectName("zxVersion")
        sync_row.addWidget(self.lbl_clock, 1)
        btn_sync = QPushButton("立即校时", page)
        btn_sync.clicked.connect(self._sync_now)
        sync_row.addWidget(btn_sync)
        outer.addLayout(sync_row)
        self.lbl_tip = QLabel("", page)
        self.lbl_tip.setFont(_ui_font(10))
        self.lbl_tip.setObjectName("zxVersion")
        self.lbl_tip.setWordWrap(True)
        outer.addWidget(self.lbl_tip)
        return page

    def _build_remote_tab(self):
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(4, 6, 4, 0)
        outer.setSpacing(7)
        self.chk_remote = QCheckBox("启用远程控制（手机/电脑控制台）", page)
        self.chk_remote.toggled.connect(self._on_remote_enabled)
        outer.addWidget(self.chk_remote)
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(QLabel("电脑名称", page))
        self.edit_remote_name = QLineEdit(page)
        self.edit_remote_name.editingFinished.connect(self._on_remote_name)
        name_row.addWidget(self.edit_remote_name, 1)
        outer.addLayout(name_row)
        desc = QLabel("手机或电脑控制台可远程修改本机课表，并发送教师通知。", page)
        desc.setFont(_ui_font(10))
        desc.setObjectName("zxVersion")
        desc.setWordWrap(True)
        outer.addWidget(desc)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        grid.addWidget(QLabel("配对码", page), 0, 0)
        self.lbl_remote_code = QLabel("------", page)
        self.lbl_remote_code.setObjectName("zxRemoteCode")
        self.lbl_remote_code.setFont(_num_font(24))
        grid.addWidget(self.lbl_remote_code, 0, 1)
        self.btn_remote_code = QPushButton("生成配对码", page)
        self.btn_remote_code.setObjectName("primary")
        self.btn_remote_code.clicked.connect(self._gen_remote_code)
        grid.addWidget(self.btn_remote_code, 0, 2)
        grid.addWidget(QLabel("本机地址", page), 1, 0)
        self.lbl_remote_addr = QLabel("尚未启用", page)
        self.lbl_remote_addr.setObjectName("zxVersion")
        self.lbl_remote_addr.setFont(_ui_font(10))
        self.lbl_remote_addr.setWordWrap(True)
        grid.addWidget(self.lbl_remote_addr, 1, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        dev_row = QHBoxLayout()
        dev_row.setSpacing(8)
        dev_title = QLabel("已配对设备", page)
        dev_title.setFont(_ui_font(11, True))
        dev_row.addWidget(dev_title)
        dev_row.addStretch(1)
        self.btn_remote_remove = QPushButton("移除选中", page)
        self.btn_remote_remove.setObjectName("danger")
        self.btn_remote_remove.clicked.connect(self._remove_remote_device)
        dev_row.addWidget(self.btn_remote_remove)
        outer.addLayout(dev_row)
        self.list_remote = QListWidget(page)
        self.list_remote.setMinimumHeight(120)
        outer.addWidget(self.list_remote, 1)
        test_row = QHBoxLayout()
        btn_test = QPushButton("测试灵动岛", page)
        btn_test.clicked.connect(self._test_island)
        test_row.addWidget(btn_test)
        test_row.addStretch(1)
        outer.addLayout(test_row)
        self.lbl_remote_tip = QLabel("在控制台输入上方配对码，电脑端确认后即可连接。配对码 5 分钟内有效，每台设备只需配对一次。", page)
        self.lbl_remote_tip.setObjectName("zxVersion")
        self.lbl_remote_tip.setFont(_ui_font(10))
        self.lbl_remote_tip.setWordWrap(True)
        outer.addWidget(self.lbl_remote_tip)
        return page

    def _on_remote_enabled(self, checked):
        if self._loading:
            return
        self._store().data.setdefault("control", {})["enabled"] = bool(checked)
        self._store().save()
        try:
            _service().apply_remote()
        except Exception:
            pass
        self._refresh_remote(True)

    def _on_remote_name(self):
        if self._loading:
            return
        name = self.edit_remote_name.text().strip() or "ZX"
        control = self._store().data.setdefault("control", {})
        control["name"] = name[:40]
        self._store().save()
        try:
            _service().apply_remote()
        except Exception:
            pass
        self._refresh_remote(True)

    def _gen_remote_code(self):
        if self._loading:
            return
        if not self.chk_remote.isChecked():
            self.chk_remote.setChecked(True)
        try:
            code, ttl = _service().generate_pair_code()
        except Exception:
            code = ""
        if not code:
            self.lbl_remote_tip.setText("远程控制启动失败，请检查端口是否被占用")
            return
        self.lbl_remote_tip.setText("配对码已生成，5 分钟内有效。请在控制台输入并按提示确认。")
        self._refresh_remote(True)

    def _remove_remote_device(self):
        try:
            item = self.list_remote.currentItem()
        except Exception:
            return
        if item is None:
            return
        device_id = str(item.data(Qt.ItemDataRole.UserRole) or "")
        if not device_id:
            return
        name = item.text().split(" · ")[0]
        if not _ask_confirm(self, "移除设备「%s」？移除后需要重新配对。" % name):
            return
        try:
            _service().remove_remote_device(device_id)
        except Exception:
            pass
        self._refresh_remote(True)

    def _seen_text(self, stamp):
        try:
            value = int(stamp or 0)
        except Exception:
            value = 0
        if value <= 0:
            return "尚未连接"
        delta = max(0, int(time.time()) - value)
        if delta < 60:
            return "刚刚在线"
        if delta < 3600:
            return "%d 分钟前" % (delta // 60)
        if delta < 86400:
            return "%d 小时前" % (delta // 3600)
        return time.strftime("%m-%d %H:%M", time.localtime(value))

    def _refresh_remote(self, force=False):
        if not hasattr(self, "lbl_remote_code"):
            return
        try:
            code, remain = _service().remote_code_state()
        except Exception:
            code, remain = "", 0.0
        if code:
            self.lbl_remote_code.setText("%s  %d:%02d" % (code, int(remain) // 60, int(remain) % 60))
        else:
            self.lbl_remote_code.setText("------")
        enabled = self.chk_remote.isChecked()
        try:
            port = _service().remote_port()
        except Exception:
            port = 0
        if enabled and port:
            ips = _local_ipv4_list()
            self.lbl_remote_addr.setText("%s · 端口 %d" % ("、".join(ips) if ips else "未联网", port))
        elif enabled:
            self.lbl_remote_addr.setText("启动失败，端口可能被占用")
        else:
            self.lbl_remote_addr.setText("尚未启用")
        try:
            rows = _service().remote_devices()
        except Exception:
            rows = []
        signature = ["%s|%s|%s|%s" % (row.get("id"), row.get("name"), row.get("platform"),
                                      row.get("last_seen")) for row in rows]
        if force or signature != getattr(self, "_remote_signature", None):
            self._remote_signature = signature
            try:
                self.list_remote.blockSignals(True)
                self.list_remote.clear()
                for row in rows:
                    text = "%s · %s · %s" % (row.get("name") or "设备",
                                             _platform_label(row.get("platform")),
                                             self._seen_text(row.get("last_seen")))
                    item = QListWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole, row.get("id") or "")
                    self.list_remote.addItem(item)
                if not rows:
                    item = QListWidgetItem("暂无已配对设备")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.list_remote.addItem(item)
            except Exception:
                return
            finally:
                try:
                    self.list_remote.blockSignals(False)
                except Exception:
                    pass

    def _on_remote_schedule(self):
        if self._loading:
            return
        store = self._store()
        self._loading = True
        mode = str(store.data.get("week_mode") or "auto")
        self.cmb_week.setCurrentIndex(max(0, self.cmb_week.findData(mode)))
        start = str(store.data.get("semester_start") or "")
        part = QDate.fromString(start, "yyyy-MM-dd") if start else self.date_start.minimumDate()
        self.date_start.setDate(part if part.isValid() else self.date_start.minimumDate())
        self._loading = False
        self._reload_plans(str(store.data.get("active") or ""))

    def _store(self):
        return _service().store

    def _load(self):
        store = self._store()
        self.cmb_plan.clear()
        for name in sorted(store.data.get("plans", {}).keys()):
            self.cmb_plan.addItem(name)
        index = self.cmb_plan.findText(str(store.data.get("active") or ""))
        self.cmb_plan.setCurrentIndex(max(0, index))
        mode = str(store.data.get("week_mode") or "auto")
        self.cmb_week.setCurrentIndex(max(0, self.cmb_week.findData(mode)))
        start = str(store.data.get("semester_start") or "")
        part = QDate.fromString(start, "yyyy-MM-dd") if start else self.date_start.minimumDate()
        self.date_start.setDate(part if part.isValid() else self.date_start.minimumDate())
        control = store.data.get("control", {})
        self.chk_remote.setChecked(bool(control.get("enabled")))
        self.edit_remote_name.setText(str(control.get("name") or ""))
        ui = store.data.get("ui", {})
        self.spin_remind.setValue(int(ui.get("remind_min", 2)))
        self.chk_sync.setChecked(bool(ui.get("time_sync", True)))
        if self.chk_sync.isChecked():
            sync_clock_async()
        self._refresh_clock_label()
        self._refresh_lessons()
        self._refresh_remote(True)

    def _refresh_lessons(self):
        if not hasattr(self, "grid_week"):
            return
        try:
            periods = _service().model.periods()
        except Exception:
            periods = [tuple(item) for item in DEFAULT_PERIODS]
        entries = self._entries()
        self.grid_week.set_data(entries, periods)
        self._refresh_activities()
        name = str(self._store().data.get("active") or DEFAULT_PLAN)
        courses = len([item for item in entries if str(item.get("kind") or "lesson") != "activity"])
        activities = len(entries) - courses
        tip = "%s · %d 门课程 · %d 个活动 · 单击空格添加，按住课程可拖动交换" % (name, courses, activities)
        if not self._store().data.get("semester_start"):
            tip += " · 单双周按自然周"
        self.lbl_tip.setText(tip)

    def _activities(self):
        return [item for item in self._entries() if str(item.get("kind") or "lesson") == "activity"]

    def _refresh_activities(self):
        if not hasattr(self, "list_activity"):
            return
        self.list_activity.clear()
        for entry in self._activities():
            label = "%s  %s - %s  %s%s" % (
                WEEKDAY_NAMES[max(0, min(6, int(entry.get("day", 1) or 1) - 1))],
                _fmt_clock(entry.get("start", 0)), _fmt_clock(entry.get("end", 0)),
                str(entry.get("name") or ""),
                (" · " + str(entry.get("room"))) if entry.get("room") else "")
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.list_activity.addItem(item)
        if not self._activities():
            hint = QListWidgetItem("暂无活动，可添加大课间、升旗仪式等")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_activity.addItem(hint)

    def _on_activity_double(self, item):
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if isinstance(entry, dict):
            self._edit_lesson(entry)

    def _on_activity_menu(self, pos):
        item = self.list_activity.itemAt(pos)
        entry = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        menu = QMenu(self)
        act_edit = menu.addAction("编辑活动")
        act_edit.setEnabled(isinstance(entry, dict))
        act_remove = menu.addAction("删除活动")
        act_remove.setEnabled(isinstance(entry, dict))
        menu.addSeparator()
        act_add = menu.addAction("添加活动")
        chosen = menu.exec(self.list_activity.mapToGlobal(pos))
        if chosen is act_add:
            self._add_activity()
        elif chosen is act_edit and isinstance(entry, dict):
            self._edit_lesson(entry)
        elif chosen is act_remove and isinstance(entry, dict):
            self._remove_entry(entry)

    def _add_activity(self):
        dialog = ZxLessonDialog(self, {"kind": "activity"}, _service().model.periods(), 1, 0)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._insert_entries(dialog.result_entries())
        self._save()
        self._refresh_lessons()

    def _on_remind_changed(self, value):
        if self._loading:
            return
        self._store().data.setdefault("ui", {})["remind_min"] = int(value)
        self._save()

    def _on_time_sync(self, checked):
        if self._loading:
            return
        self._store().data.setdefault("ui", {})["time_sync"] = bool(checked)
        self._save()
        if checked:
            sync_clock_async()
        self._refresh_clock_label()

    def _sync_now(self):
        self._store().data.setdefault("ui", {})["time_sync"] = True
        self._store().save()
        if not self.chk_sync.isChecked():
            self.chk_sync.setChecked(True)
        sync_clock_async()
        _log("ZX 手动校时")

    def _refresh_clock_label(self):
        if not hasattr(self, "lbl_clock"):
            return
        offset = clock_offset()
        text = clock_status_text()
        if abs(offset) >= 0.5:
            text += " · 当前 %s" % _now().strftime("%H:%M:%S")
        self.lbl_clock.setText(text)

    def _on_entry_dropped(self, from_day, from_period, to_day, to_period):
        entries = self._entries()
        source = None
        target = None
        for entry in entries:
            if str(entry.get("kind") or "lesson") == "activity":
                continue
            if int(entry.get("day", 0) or 0) == from_day and int(entry.get("period", 0) or 0) == from_period:
                source = entry
            elif int(entry.get("day", 0) or 0) == to_day and int(entry.get("period", 0) or 0) == to_period:
                target = entry
        if source is None:
            return
        if target is None:
            source["day"] = to_day
            source["period"] = to_period
            source.pop("start", None)
            source.pop("end", None)
        else:
            target["day"] = from_day
            target["period"] = from_period
            for item in (source, target):
                item.pop("start", None)
                item.pop("end", None)
            source["day"] = to_day
            source["period"] = to_period
        self._save()
        self._refresh_lessons()

    def _entries(self, create=False):
        store = self._store()
        active = str(store.data.get("active") or "")
        plans = store.data.setdefault("plans", {})
        if active not in plans:
            plans[active] = []
        return plans[active]

    def _entry_at(self, day, period):
        for entry in self._entries():
            if str(entry.get("kind") or "lesson") == "activity":
                continue
            if int(entry.get("day", 0) or 0) == day and int(entry.get("period", 0) or 0) == period:
                return entry
        return None

    def _insert_entries(self, rows):
        if not rows:
            return
        occupied = set()
        for row in rows:
            if str(row.get("kind") or "lesson") == "activity":
                continue
            occupied.add((int(row["day"]), int(row["period"])))
        entries = self._entries(True)
        entries[:] = [item for item in entries
                      if str(item.get("kind") or "lesson") == "activity"
                      or (int(item.get("day", 0) or 0), int(item.get("period", 0) or 0)) not in occupied]
        entries.extend(rows)

    def _remove_entry(self, entry):
        entries = self._entries()
        for index, candidate in enumerate(entries):
            if candidate is entry:
                entries.pop(index)
                break
        self._save()
        self._refresh_lessons()

    def _clear_plan(self):
        name = str(self._store().data.get("active") or "")
        if not _ask_confirm(self, "清空方案「%s」的全部课程？" % name):
            return
        self._entries(True).clear()
        self._save()
        self._refresh_lessons()

    def _on_cell(self, day, period):
        entry = self._entry_at(day, period)
        if entry is None:
            self._add_lesson(day, period)
        else:
            self._edit_lesson(entry)

    def _on_cell_menu(self, day, period, pos):
        entry = self._entry_at(day, period)
        menu = QMenu(self)
        act_edit = menu.addAction("编辑课程" if entry is not None else "添加课程")
        act_remove = menu.addAction("删除本节")
        act_remove.setEnabled(entry is not None)
        menu.addSeparator()
        act_day = menu.addAction("清空 %s" % WEEKDAY_NAMES[day - 1])
        chosen = menu.exec(pos)
        if chosen is act_edit:
            self._on_cell(day, period)
        elif chosen is act_remove:
            self._remove_entry(entry)
        elif chosen is act_day:
            entries = self._entries()
            entries[:] = [item for item in entries
                          if str(item.get("kind") or "lesson") == "activity"
                          or int(item.get("day", 0) or 0) != day]
            self._save()
            self._refresh_lessons()

    def _save(self):
        self._store().save()
        try:
            _service().refresh_model()
        except Exception:
            pass

    def _on_plan_changed(self, name):
        if self._loading or not name:
            return
        self._store().data["active"] = name
        self._save()
        self._refresh_lessons()

    def _reload_plans(self, select):
        self._loading = True
        self.cmb_plan.clear()
        for name in sorted(self._store().data.get("plans", {}).keys()):
            self.cmb_plan.addItem(name)
        index = self.cmb_plan.findText(str(select or ""))
        self.cmb_plan.setCurrentIndex(max(0, index))
        self._loading = False
        self._refresh_lessons()

    def _new_plan(self):
        text, ok = _ask_text(self, "新建方案", "方案名称")
        name = str(text or "").strip()
        if not ok or not name:
            return
        plans = self._store().data.setdefault("plans", {})
        if name in plans:
            _styled_box(self, QMessageBox.Icon.Information, "该方案已存在")
            return
        plans[name] = []
        self._store().data["active"] = name
        self._save()
        self._reload_plans(name)

    def _rename_plan(self):
        current = str(self._store().data.get("active") or "")
        if not current:
            return
        text, ok = _ask_text(self, "重命名方案", "方案名称", current)
        name = str(text or "").strip()
        if not ok or not name or name == current:
            return
        plans = self._store().data.setdefault("plans", {})
        if name in plans:
            _styled_box(self, QMessageBox.Icon.Information, "该方案已存在")
            return
        plans[name] = plans.pop(current)
        self._store().data["active"] = name
        self._save()
        self._reload_plans(name)

    def _delete_plan(self):
        store = self._store()
        current = str(store.data.get("active") or "")
        plans = store.data.setdefault("plans", {})
        if len(plans) <= 1:
            _styled_box(self, QMessageBox.Icon.Information, "至少保留一个方案")
            return
        if not _ask_confirm(self, "删除方案「%s」？" % current):
            return
        plans.pop(current, None)
        store.data["active"] = sorted(plans.keys())[0]
        self._save()
        self._reload_plans(store.data["active"])

    def _on_week_mode(self, index):
        if self._loading:
            return
        key = str(self.cmb_week.itemData(index) or "auto")
        self._store().data["week_mode"] = key
        self._save()
        self._refresh_lessons()

    def _on_semester_start(self, value):
        if self._loading:
            return
        if value == self.date_start.minimumDate():
            self._store().data["semester_start"] = ""
        else:
            self._store().data["semester_start"] = value.toString("yyyy-MM-dd")
        self._save()
        self._refresh_lessons()

    def _add_lesson(self, day=1, period=0):
        dialog = ZxLessonDialog(self, None, _service().model.periods(), day, period)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._insert_entries(dialog.result_entries())
        self._save()
        self._refresh_lessons()

    def _edit_lesson(self, entry=None):
        if not isinstance(entry, dict):
            return
        day = int(entry.get("day", 1) or 1)
        period = int(entry.get("period", 0) or 0)
        dialog = ZxLessonDialog(self, entry, _service().model.periods(), day, period)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entries = self._entries()
        for index, candidate in enumerate(entries):
            if candidate is entry:
                entries.pop(index)
                break
        self._insert_entries(dialog.result_entries())
        self._save()
        self._refresh_lessons()

    def _edit_periods(self, index=0):
        dialog = ZxPeriodsDialog(self, _service().model.periods(), index)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._store().data["periods"] = dialog.result_periods()
        self._save()
        self._refresh_lessons()

    def _test_island(self):
        try:
            _service().notify("ZX 提醒", "灵动岛工作正常，上课前会自动展开提醒你", "success")
        except Exception:
            pass


class ZxService(QObject):
    remote_schedule_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.store = ZxStore()
        self.model = ZxSchedule(self.store)
        self.island = None
        self.remote = None
        self.notifier = None
        self._pair_dialog = None
        self.fired = set()
        self.day_key = ""
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.clock_timer = QTimer(self)
        self.clock_timer.setInterval(1800000)
        self.clock_timer.timeout.connect(self._sync_clock_tick)
        self.net = None
        self._time_replies = []

    def start(self):
        self.store.load()
        self.model = ZxSchedule(self.store)
        self.timer.start()
        self.apply_remote()
        if bool(self.store.data.get("ui", {}).get("time_sync", True)):
            sync_clock_async()
            self.clock_timer.start()
        self._tick()

    def _sync_clock_tick(self):
        if bool(self.store.data.get("ui", {}).get("time_sync", True)):
            sync_clock_async()

    def sync_time(self):
        global _CLOCK_BUSY
        if _CLOCK_BUSY:
            return False
        if self.net is None:
            self.net = QNetworkAccessManager(self)
        _CLOCK_BUSY = True
        self._time_replies = []
        for name, url, kind in _CLOCK_SOURCES:
            request = QNetworkRequest(QUrl(url))
            request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0")
            reply = self.net.get(request)
            reply.setProperty("zx_source", name)
            reply.setProperty("zx_kind", kind)
            reply.setProperty("zx_started", time.time())
            reply.finished.connect(lambda r=reply: self._on_time_reply(r))
            self._time_replies.append(reply)
        QTimer.singleShot(6000, self._time_sync_timeout)
        return True

    def _on_time_reply(self, reply):
        if reply not in self._time_replies:
            return
        self._time_replies.remove(reply)
        source = str(reply.property("zx_source") or "")
        kind = str(reply.property("zx_kind") or "")
        started = float(reply.property("zx_started") or time.time())
        rtt = max(0.0, time.time() - started)
        epoch = None
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                body = bytes(reply.readAll()).decode("utf-8", "ignore")
                epoch = _epoch_from_payload(kind, body, reply)
        except Exception:
            epoch = None
        reply.deleteLater()
        if epoch is None:
            if not self._time_replies:
                _clock_fail("时间接口不可用")
            return
        for other in list(self._time_replies):
            try:
                other.abort()
            except Exception:
                pass
        self._time_replies = []
        _apply_clock_offset(epoch - (started + rtt / 2.0), source, rtt)

    def _time_sync_timeout(self):
        if not self._time_replies:
            return
        for other in list(self._time_replies):
            try:
                other.abort()
            except Exception:
                pass
        self._time_replies = []
        _clock_fail("时间接口超时")

    def stop(self):
        self.timer.stop()
        self.clock_timer.stop()
        if self.remote is not None:
            self.remote.stop()
            self.remote = None
        if self.notifier is not None:
            self.notifier.close_all()
        if self._pair_dialog is not None:
            try:
                self._pair_dialog.reject()
            except Exception:
                pass
            self._pair_dialog = None
        if self.island is not None:
            try:
                self.island.hide()
                self.island.deleteLater()
            except Exception:
                pass
            self.island = None

    def apply_remote(self):
        enabled = bool(self.store.data.get("control", {}).get("enabled"))
        if enabled:
            if self.remote is None:
                self.remote = ZxRemoteServer(self.store, self.schedule_state,
                                             self.apply_remote_schedule, self)
                self.remote.pair_requested.connect(self._on_remote_pair_request)
                self.remote.notice.connect(self._on_remote_notice)
                self.remote.schedule_changed.connect(self._on_remote_schedule_saved)
            self.remote.start()
        elif self.remote is not None:
            self.remote.stop()
            self.remote = None

    def generate_pair_code(self):
        if self.remote is None:
            self.store.data.setdefault("control", {})["enabled"] = True
            self.store.save()
            self.apply_remote()
        if self.remote is None:
            return "", 0.0
        return self.remote.generate_code()

    def remote_code_state(self):
        if self.remote is None:
            return "", 0.0
        return self.remote.code_state()

    def remote_port(self):
        if self.remote is None:
            return 0
        return int(self.remote.port)

    def remote_devices(self):
        if self.remote is not None:
            return self.remote.device_rows()
        rows = []
        for item in self.store.data.get("control", {}).get("devices") or []:
            if isinstance(item, dict):
                rows.append({
                    "id": str(item.get("id") or ""),
                    "name": str(item.get("name") or "设备"),
                    "platform": str(item.get("platform") or "unknown"),
                    "paired_at": int(item.get("paired_at") or 0),
                    "last_seen": int(item.get("last_seen") or 0),
                })
        return rows

    def remove_remote_device(self, device_id):
        if self.remote is not None:
            return self.remote.remove_device(device_id)
        cfg = self.store.data.get("control")
        if not isinstance(cfg, dict):
            return False
        target = str(device_id or "")
        before = len(cfg.get("devices") or [])
        cfg["devices"] = [item for item in cfg.get("devices") or []
                          if str(item.get("id") or "") != target]
        if len(cfg["devices"]) == before:
            return False
        self.store.save()
        self.remote_schedule_changed.emit()
        return True

    def schedule_state(self):
        data = self.store.data
        try:
            return json.loads(json.dumps({
                "plans": data.get("plans") or {},
                "active": data.get("active") or "",
                "periods": data.get("periods") or [],
                "week_mode": data.get("week_mode") or "auto",
                "semester_start": data.get("semester_start") or "",
                "overrides": data.get("overrides") or {},
            }, ensure_ascii=False))
        except Exception:
            return {}

    def schedule_rev(self):
        return _state_rev(self.schedule_state())

    def apply_remote_schedule(self, state, base_rev="", force=False):
        if not isinstance(state, dict):
            return False, {"rev": self.schedule_rev(), "state": self.schedule_state(),
                           "message": "课表数据格式错误"}
        rev = self.schedule_rev()
        if base_rev and base_rev != rev and not force:
            return False, {"rev": rev, "state": self.schedule_state(),
                           "message": "电脑端课表已变化"}
        plans = state.get("plans")
        periods = state.get("periods")
        if not isinstance(plans, dict) or not isinstance(periods, list):
            return False, {"rev": rev, "state": self.schedule_state(),
                           "message": "课表数据不完整"}
        data = self.store.data
        data["plans"] = plans
        data["active"] = str(state.get("active") or "")
        data["periods"] = periods
        data["week_mode"] = str(state.get("week_mode") or "auto")
        data["semester_start"] = str(state.get("semester_start") or "")
        if isinstance(state.get("overrides"), dict):
            data["overrides"] = state.get("overrides")
        self.store._normalize()
        self.store.save()
        self.refresh_model()
        self.remote_schedule_changed.emit()
        return True, self.schedule_rev()

    def _on_remote_schedule_saved(self):
        self.remote_schedule_changed.emit()

    def _on_remote_pair_request(self, device, ip, request_id):
        remote = self.remote
        if remote is None:
            return
        if self._pair_dialog is not None:
            remote.resolve_pair(request_id, False)
            return
        dialog = ZxPairDialog(device, ip)
        self._pair_dialog = dialog
        try:
            remote.pair_resolved.connect(dialog.reject)
        except Exception:
            pass
        try:
            result = dialog.exec()
        finally:
            try:
                remote.pair_resolved.disconnect(dialog.reject)
            except Exception:
                pass
            self._pair_dialog = None
        remote.resolve_pair(request_id, result == QDialog.DialogCode.Accepted)

    def _on_remote_notice(self, title, body, sender, duration=8.0):
        if self.notifier is None:
            self.notifier = ZxRemoteNotifier()
        self.notifier.show(title, body, sender, duration)

    def refresh_model(self):
        self.model = ZxSchedule(self.store)

    def notify(self, title, body, tone="accent", sticky=False):
        if not bool(self.store.data.get("ui", {}).get("island", True)):
            return
        if self.island is None:
            self.island = ZxIsland()
        self.island.show_notice(title, body, tone, sticky)

    def _tick(self):
        snap = self.model.snapshot()
        self._remind(snap)

    def _remind(self, snap):
        key_day = snap["today"].strftime("%Y%m%d")
        if key_day != self.day_key:
            self.day_key = key_day
            self.fired.clear()
        remind = int(self.store.data.get("ui", {}).get("remind_min", 2)) * 60
        if snap["state"] == "class":
            item = snap["current"]
            remain = snap["remain"]
            key = "end:%s:%s" % (item.get("kind"), item["period"])
            if 0 < remain <= remind and key not in self.fired:
                self.fired.add(key)
                self.notify("即将下课", "%s · %s 下课" % (item["name"], _fmt_clock(item["end"])), "warn")
        elif snap["state"] == "break":
            item = snap["next"]
            remain = snap["remain"]
            key = "start:%s:%s" % (item.get("kind"), item["period"])
            if 0 < remain <= remind and key not in self.fired:
                self.fired.add(key)
                self.notify("即将开始", "%s · %s 开始" % (item["name"], _fmt_clock(item["start"])), "accent")


def _service():
    global SERVICE
    if SERVICE is None:
        SERVICE = ZxService()
    return SERVICE


def _tray_today(context=None):
    open_day_dialog()


class ZxPlugin(Plugin):
    def __init__(self):
        super().__init__()
        self.name = "ZX"
        self.version = VERSION
        self.build_version = BUILD_VERSION
        self.author = "苗睿轩"
        self.description = "课程表悬浮窗、上课下课灵动岛提醒与远程控制台"

    def on_enable(self):
        _service().start()

    def on_disable(self):
        if SERVICE is not None:
            SERVICE.stop()


def setup(app, api):
    global API, APP
    APP = app
    API = api
    api.register_float_widget("zx_schedule", "ZX 课程表", ZxScheduleWidget, (300, 168),
                              "上课进度、下一节课与课间提醒", False)
    page_api = getattr(api, "register_settings_page", None)
    if page_api is None:
        page_api = getattr(api, "register_settings_panel", None)
    if page_api is not None:
        try:
            page_api("zx_settings", "ZX 智能助手", ZxSettingsPage, (980, 720))
        except TypeError:
            page_api("zx_settings", "ZX 智能助手", ZxSettingsPage)
    action_api = getattr(api, "register_action", None)
    if action_api is not None:
        action_api("tray_menu", "zx_today_timetable", "ZX 今日课表", _tray_today)
    return ZxPlugin()

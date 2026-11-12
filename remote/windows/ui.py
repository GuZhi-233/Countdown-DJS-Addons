import copy
import json
import os
import socket
import time
import uuid

from PyQt6.QtCore import QDate, QTime, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QGuiApplication
from PyQt6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox,
                             QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
                             QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
                             QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                             QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                             QSpinBox, QStackedWidget, QTextEdit, QTimeEdit,
                             QVBoxLayout, QWidget)

from net import Discovery, RemoteClient
from sessions import DeviceManager
from theme import colors, is_system_dark, lesson_color, qss
from version import APP_NAME, BUILD_VERSION, DEFAULT_CONTROL_PORT, VERSION

WEEK_LABELS = {"all": "每周", "odd": "单周", "even": "双周"}
WEEK_MODES = {"auto": "按周次自动", "odd": "只看单周", "even": "只看双周"}
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
DEFAULT_PERIODS = [[450, 490], [500, 540], [550, 590], [610, 650], [660, 700],
                   [840, 880], [890, 930], [940, 980], [990, 1030], [1140, 1180]]


def _label(text, dim=False, bold=False):
    widget = QLabel(str(text))
    if dim:
        widget.setObjectName("dim")
    if bold:
        font = widget.font()
        font.setBold(True)
        widget.setFont(font)
    return widget


def _clock_text(minutes):
    value = int(round(minutes))
    return "%02d:%02d" % (value // 60 % 24, value % 60)


def _time_minutes(widget):
    value = widget.time()
    return value.hour() * 60 + value.minute()


class Config:
    def __init__(self):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        self.path = os.path.join(base, "ZXRemote", "config.json")
        self.data = {
            "device_id": uuid.uuid4().hex,
            "device_name": socket.gethostname() or "Windows 电脑",
            "hosts": [],
            "last_host": "",
            "theme": "system",
            "history": [],
        }
        self.load()

    def load(self):
        raw = {}
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            for key in ("device_id", "device_name", "last_host", "theme"):
                value = raw.get(key)
                if isinstance(value, str) and value:
                    self.data[key] = value
            if isinstance(raw.get("hosts"), list):
                self.data["hosts"] = [item for item in raw["hosts"] if isinstance(item, dict)]
            if isinstance(raw.get("history"), list):
                self.data["history"] = [item for item in raw["history"]
                                        if isinstance(item, dict)][:20]
        if not self.data.get("device_id"):
            self.data["device_id"] = uuid.uuid4().hex
        if not self.data.get("device_name"):
            self.data["device_name"] = "Windows 电脑"

    def save(self):
        try:
            folder = os.path.dirname(self.path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def find_host(self, host_id):
        target = str(host_id or "")
        for item in self.data.get("hosts") or []:
            if str(item.get("id") or "") == target:
                return item
        return None

    def remember_host(self, entry):
        target = str(entry.get("id") or "")
        rows = [item for item in self.data.get("hosts") or []
                if str(item.get("id") or "") != target]
        rows.append(entry)
        self.data["hosts"] = rows
        self.data["last_host"] = target
        self.save()

    def forget_host(self, host_id):
        target = str(host_id or "")
        self.data["hosts"] = [item for item in self.data.get("hosts") or []
                              if str(item.get("id") or "") != target]
        if str(self.data.get("last_host") or "") == target:
            self.data["last_host"] = ""
        self.save()


class PairDialog(QDialog):
    def __init__(self, parent, host_name, address, device_name):
        super().__init__(parent)
        self.setWindowTitle("配对 ZX")
        self.resize(420, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(10)
        layout.addWidget(_label("与 %s 配对" % (host_name or "ZX"), bold=True))
        layout.addWidget(_label("%s" % address, dim=True))
        layout.addWidget(_label("请输入电脑端“远程”页生成的 6 位配对码。电脑端确认后即可连接。"))
        self.edit_code = QLineEdit(self)
        self.edit_code.setMaxLength(6)
        self.edit_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.edit_code.setPlaceholderText("6 位配对码")
        font = self.edit_code.font()
        font.setPointSize(20)
        font.setBold(True)
        self.edit_code.setFont(font)
        layout.addWidget(self.edit_code)
        form = QFormLayout()
        form.setSpacing(8)
        self.edit_name = QLineEdit(device_name, self)
        form.addRow("设备名称", self.edit_name)
        layout.addLayout(form)
        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                               QDialogButtonBox.StandardButton.Ok, self)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("确认配对")
        box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.edit_code.setFocus()

    def accept(self):
        if len(self.edit_code.text().strip()) != 6:
            QMessageBox.warning(self, "配对码", "请输入 6 位配对码")
            return
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "设备名称", "请输入设备名称")
            return
        super().accept()

    def values(self):
        return self.edit_code.text().strip(), self.edit_name.text().strip()


class LessonDialog(QDialog):
    def __init__(self, parent, entry, day, period, periods, activity=False):
        super().__init__(parent)
        self.setWindowTitle("编辑课程" if not activity else "编辑活动")
        self.resize(420, 320)
        self._entry = entry if isinstance(entry, dict) else None
        self._day = int(day)
        self._period = int(period)
        self._periods = periods
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        form = QFormLayout()
        form.setSpacing(8)
        self.cmb_kind = QComboBox(self)
        self.cmb_kind.addItem("课程", "lesson")
        self.cmb_kind.addItem("活动", "activity")
        form.addRow("类型", self.cmb_kind)
        self.edit_name = QLineEdit(self)
        form.addRow("名称", self.edit_name)
        self.edit_room = QLineEdit(self)
        form.addRow("教室", self.edit_room)
        self.cmb_weeks = QComboBox(self)
        for key, text in WEEK_LABELS.items():
            self.cmb_weeks.addItem(text, key)
        form.addRow("周次", self.cmb_weeks)
        layout.addLayout(form)
        self.time_row = QWidget(self)
        time_layout = QHBoxLayout(self.time_row)
        time_layout.setContentsMargins(0, 0, 0, 0)
        time_layout.setSpacing(8)
        self.edit_start = QTimeEdit(self.time_row)
        self.edit_end = QTimeEdit(self.time_row)
        self.edit_start.setDisplayFormat("HH:mm")
        self.edit_end.setDisplayFormat("HH:mm")
        time_layout.addWidget(QLabel("开始", self.time_row))
        time_layout.addWidget(self.edit_start)
        time_layout.addWidget(QLabel("结束", self.time_row))
        time_layout.addWidget(self.edit_end)
        time_layout.addStretch(1)
        layout.addWidget(self.time_row)
        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                               QDialogButtonBox.StandardButton.Ok, self)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        start_default = 450
        end_default = 490
        if 0 <= self._period < len(periods):
            start_default, end_default = periods[self._period]
        if self._entry:
            self.edit_name.setText(str(self._entry.get("name") or ""))
            self.edit_room.setText(str(self._entry.get("room") or ""))
            self.cmb_weeks.setCurrentIndex(max(0, self.cmb_weeks.findData(
                str(self._entry.get("weeks") or "all"))))
            kind = "activity" if str(self._entry.get("kind") or "") == "activity" else "lesson"
            self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(kind)))
            if kind == "activity":
                start_default = int(self._entry.get("start") or start_default)
                end_default = int(self._entry.get("end") or end_default)
        self.edit_start.setTime(QTime(start_default // 60, start_default % 60))
        self.edit_end.setTime(QTime(end_default // 60, end_default % 60))
        self.cmb_kind.currentIndexChanged.connect(self._sync_kind)
        self._sync_kind()

    def _sync_kind(self):
        is_activity = self.cmb_kind.currentData() == "activity"
        self.time_row.setVisible(is_activity)

    def accept(self):
        if not self.edit_name.text().strip():
            QMessageBox.warning(self, "名称", "请输入课程或活动名称")
            return
        if self.cmb_kind.currentData() == "activity":
            if _time_minutes(self.edit_start) >= _time_minutes(self.edit_end):
                QMessageBox.warning(self, "时间", "结束时间必须晚于开始时间")
                return
        super().accept()

    def result_entry(self):
        kind = str(self.cmb_kind.currentData() or "lesson")
        entry = {
            "day": self._day,
            "period": self._period,
            "name": self.edit_name.text().strip(),
            "room": self.edit_room.text().strip(),
            "weeks": str(self.cmb_weeks.currentData() or "all"),
            "kind": kind,
        }
        if kind == "activity":
            entry["start"] = _time_minutes(self.edit_start)
            entry["end"] = _time_minutes(self.edit_end)
        elif self._entry and self._entry.get("start") is not None and self._entry.get("end") is not None:
            entry["start"] = int(self._entry.get("start"))
            entry["end"] = int(self._entry.get("end"))
        return entry


class CellDialog(QDialog):
    def __init__(self, parent, plan_entries, day, period, periods, on_changed):
        super().__init__(parent)
        self.setWindowTitle("编辑格子")
        self.resize(470, 400)
        self._entries = plan_entries
        self._day = int(day)
        self._period = int(period)
        self._periods = periods
        self._on_changed = on_changed
        self._items = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        layout.addWidget(_label("%s · 第 %d 节" % (WEEKDAY_NAMES[max(0, min(6, self._day - 1))],
                                                  self._period + 1), bold=True))
        self.list_entries = QListWidget(self)
        self.list_entries.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_entries.itemDoubleClicked.connect(lambda item: self._edit())
        layout.addWidget(self.list_entries, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        btn_lesson = QPushButton("新增课程", self)
        btn_lesson.setObjectName("primary")
        btn_lesson.clicked.connect(lambda: self._add(False))
        row.addWidget(btn_lesson)
        btn_activity = QPushButton("新增活动", self)
        btn_activity.clicked.connect(lambda: self._add(True))
        row.addWidget(btn_activity)
        row.addStretch(1)
        btn_edit = QPushButton("编辑", self)
        btn_edit.clicked.connect(self._edit)
        row.addWidget(btn_edit)
        btn_delete = QPushButton("删除", self)
        btn_delete.setObjectName("danger")
        btn_delete.clicked.connect(self._delete)
        row.addWidget(btn_delete)
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.reject)
        row.addWidget(btn_close)
        layout.addLayout(row)
        self._reload()

    def _cell_entries(self):
        return [entry for entry in self._entries
                if int(entry.get("day", 0) or 0) == self._day
                and int(entry.get("period", 0) or 0) == self._period]

    def _reload(self):
        self.list_entries.clear()
        self._items = self._cell_entries()
        for entry in self._items:
            kind = "活动" if str(entry.get("kind") or "") == "activity" else "课程"
            room = str(entry.get("room") or "").strip() or "未填教室"
            weeks = WEEK_LABELS.get(str(entry.get("weeks") or "all"), "每周")
            text = "%s · %s · %s · %s" % (kind, entry.get("name") or "未命名", room, weeks)
            if kind == "活动":
                text += " · %s-%s" % (_clock_text(entry.get("start") or 0),
                                       _clock_text(entry.get("end") or 0))
            item = QListWidgetItem(text)
            self.list_entries.addItem(item)
        if not self._items:
            item = QListWidgetItem("这个格子还没有内容")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_entries.addItem(item)

    def _selected_entry(self):
        row = self.list_entries.currentRow()
        if row < 0 or row >= len(self._items):
            return None
        return self._items[row]

    def _add(self, activity):
        dialog = LessonDialog(self, None, self._day, self._period, self._periods, activity)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dialog.result_entry()
        if entry:
            self._entries.append(entry)
            self._on_changed()
            self._reload()

    def _edit(self):
        entry = self._selected_entry()
        if entry is None:
            return
        activity = str(entry.get("kind") or "") == "activity"
        dialog = LessonDialog(self, entry, self._day, self._period, self._periods, activity)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        updated = dialog.result_entry()
        for index, item in enumerate(self._entries):
            if item is entry:
                self._entries[index] = updated
                break
        self._on_changed()
        self._reload()

    def _delete(self):
        entry = self._selected_entry()
        if entry is None:
            return
        if QMessageBox.question(self, "删除", "删除「%s」？" % (entry.get("name") or "未命名")) != \
                QMessageBox.StandardButton.Yes:
            return
        for index, item in enumerate(self._entries):
            if item is entry:
                self._entries.pop(index)
                break
        self._on_changed()
        self._reload()


class PeriodsDialog(QDialog):
    def __init__(self, parent, periods):
        super().__init__(parent)
        self.setWindowTitle("节次时间")
        self.resize(430, 560)
        self._rows = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        layout.addWidget(_label("设置每一节的开始与结束时间", bold=True))
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        holder = QWidget(scroll)
        self.rows_layout = QVBoxLayout(holder)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(7)
        scroll.setWidget(holder)
        layout.addWidget(scroll, 1)
        for item in periods:
            self._add_row(int(item[0]), int(item[1]))
        row = QHBoxLayout()
        btn_add = QPushButton("新增一节", self)
        btn_add.clicked.connect(lambda: self._add_row(450, 490))
        row.addWidget(btn_add)
        row.addStretch(1)
        layout.addLayout(row)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                               QDialogButtonBox.StandardButton.Ok, self)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _add_row(self, start, end):
        if len(self._rows) >= 24:
            return
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        index = len(self._rows) + 1
        row.addWidget(QLabel("第 %d 节" % index, holder))
        edit_start = QTimeEdit(holder)
        edit_end = QTimeEdit(holder)
        edit_start.setDisplayFormat("HH:mm")
        edit_end.setDisplayFormat("HH:mm")
        edit_start.setTime(QTime(max(0, start) // 60, max(0, start) % 60))
        edit_end.setTime(QTime(max(0, end) // 60, max(0, end) % 60))
        row.addWidget(edit_start)
        row.addWidget(QLabel("—", holder))
        row.addWidget(edit_end)
        row.addStretch(1)
        btn = QPushButton("删除", holder)
        btn.setObjectName("danger")
        btn.clicked.connect(lambda: self._remove_row(holder))
        row.addWidget(btn)
        self.rows_layout.addWidget(holder)
        self._rows.append((holder, edit_start, edit_end))

    def _remove_row(self, holder):
        for index, item in enumerate(list(self._rows)):
            if item[0] is holder:
                self._rows.pop(index)
                break
        holder.deleteLater()
        for index, item in enumerate(self._rows):
            label = item[0].findChild(QLabel)
            if label is not None:
                label.setText("第 %d 节" % (index + 1))

    def accept(self):
        values = []
        for holder, edit_start, edit_end in self._rows:
            start = _time_minutes(edit_start)
            end = _time_minutes(edit_end)
            if start >= end:
                QMessageBox.warning(self, "节次时间", "结束时间必须晚于开始时间")
                return
            values.append([start, end])
        if not values:
            QMessageBox.warning(self, "节次时间", "至少保留一节")
            return
        super().accept()

    def result_periods(self):
        return [[_time_minutes(edit_start), _time_minutes(edit_end)]
                for holder, edit_start, edit_end in self._rows]


class SemesterDialog(QDialog):
    def __init__(self, parent, semester_start, week_mode):
        super().__init__(parent)
        self.setWindowTitle("学期与周次")
        self.resize(400, 240)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        self.chk_start = QCheckBox("设置学期开始日期", self)
        layout.addWidget(self.chk_start)
        self.edit_date = QDateEdit(self)
        self.edit_date.setCalendarPopup(True)
        self.edit_date.setDisplayFormat("yyyy-MM-dd")
        self.edit_date.setDate(QDate.currentDate())
        layout.addWidget(self.edit_date)
        form = QFormLayout()
        self.cmb_mode = QComboBox(self)
        for key, text in WEEK_MODES.items():
            self.cmb_mode.addItem(text, key)
        form.addRow("单双周", self.cmb_mode)
        layout.addLayout(form)
        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                               QDialogButtonBox.StandardButton.Ok, self)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("保存")
        box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        text = str(semester_start or "")
        part = QDate.fromString(text, "yyyy-MM-dd")
        if text and part.isValid():
            self.chk_start.setChecked(True)
            self.edit_date.setDate(part)
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(str(week_mode or "auto"))))
        self.chk_start.toggled.connect(self.edit_date.setEnabled)
        self.edit_date.setEnabled(self.chk_start.isChecked())

    def result_values(self):
        start = self.edit_date.date().toString("yyyy-MM-dd") if self.chk_start.isChecked() else ""
        return start, str(self.cmb_mode.currentData() or "auto")


class SchedulePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.on_refresh = None
        self.on_save = None
        self.on_save_force = None
        self.state = {}
        self.rev = ""
        self.dirty = False
        self._loading = False
        self._enabled = True
        self._plan_entries = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.addWidget(_label("方案"))
        self.cmb_plan = QComboBox(self)
        self.cmb_plan.setMinimumWidth(150)
        self.cmb_plan.currentTextChanged.connect(self._on_plan_changed)
        toolbar.addWidget(self.cmb_plan)
        btn_new = QPushButton("新建", self)
        btn_new.clicked.connect(self._new_plan)
        toolbar.addWidget(btn_new)
        btn_rename = QPushButton("重命名", self)
        btn_rename.clicked.connect(self._rename_plan)
        toolbar.addWidget(btn_rename)
        btn_delete = QPushButton("删除", self)
        btn_delete.clicked.connect(self._delete_plan)
        toolbar.addWidget(btn_delete)
        toolbar.addStretch(1)
        self.lbl_status = _label("尚未连接", dim=True)
        toolbar.addWidget(self.lbl_status)
        self.btn_refresh = QPushButton("刷新", self)
        self.btn_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(self.btn_refresh)
        self.btn_save = QPushButton("保存到 ZX", self)
        self.btn_save.setObjectName("primary")
        self.btn_save.clicked.connect(self._save)
        toolbar.addWidget(self.btn_save)
        layout.addLayout(toolbar)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self._holder = QWidget(self.scroll)
        self.grid = QGridLayout(self._holder)
        self.grid.setContentsMargins(4, 4, 4, 4)
        self.grid.setHorizontalSpacing(5)
        self.grid.setVerticalSpacing(5)
        self.scroll.setWidget(self._holder)
        layout.addWidget(self.scroll, 1)
        bottom = QHBoxLayout()
        bottom.setSpacing(8)
        btn_periods = QPushButton("节次设置", self)
        btn_periods.clicked.connect(self._edit_periods)
        bottom.addWidget(btn_periods)
        btn_semester = QPushButton("学期与周次", self)
        btn_semester.clicked.connect(self._edit_semester)
        bottom.addWidget(btn_semester)
        bottom.addStretch(1)
        bottom.addWidget(_label("点击格子添加或编辑课程与活动", dim=True))
        layout.addLayout(bottom)

    def load_state(self, state, rev, force=False):
        if self.dirty and not force:
            self.lbl_status.setText("电脑端课表已更新，保存前请先刷新")
            return False
        self.state = copy.deepcopy(state or {})
        self.rev = str(rev or "")
        self.dirty = False
        self._loading = True
        plans = self.state.get("plans")
        if not isinstance(plans, dict):
            plans = {}
            self.state["plans"] = plans
        if not plans:
            plans["我的课表"] = []
        active = str(self.state.get("active") or "")
        if active not in plans:
            active = sorted(plans.keys())[0]
            self.state["active"] = active
        self.cmb_plan.clear()
        for name in sorted(plans.keys()):
            self.cmb_plan.addItem(name)
        self.cmb_plan.setCurrentIndex(max(0, self.cmb_plan.findText(active)))
        self._loading = False
        self._plan_entries = plans.setdefault(active, [])
        self._rebuild_grid()
        self._update_status()
        return True

    def _periods(self):
        rows = self.state.get("periods")
        if not isinstance(rows, list) or not rows:
            rows = DEFAULT_PERIODS
        values = []
        for item in rows:
            try:
                values.append((int(item[0]), int(item[1])))
            except Exception:
                continue
        return values or [tuple(item) for item in DEFAULT_PERIODS]

    def _rebuild_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        days = len(WEEKDAY_NAMES)
        self.grid.addWidget(_label("节次", dim=True), 0, 0)
        for index, name in enumerate(WEEKDAY_NAMES):
            label = _label(name, bold=True)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.grid.addWidget(label, 0, index + 1)
            self.grid.setColumnStretch(index + 1, 1)
        periods = self._periods()
        for period, (start, end) in enumerate(periods):
            head = _label("%d\n%s" % (period + 1, _clock_text(start)), dim=True)
            head.setAlignment(Qt.AlignmentFlag.AlignCenter)
            head.setToolTip("%s-%s" % (_clock_text(start), _clock_text(end)))
            head.setMinimumWidth(52)
            self.grid.addWidget(head, period + 1, 0)
            for day in range(1, days + 1):
                entries = [entry for entry in self._plan_entries
                           if int(entry.get("day", 0) or 0) == day
                           and int(entry.get("period", 0) or 0) == period]
                button = QPushButton(self._holder)
                button.setMinimumHeight(52)
                button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
                if entries:
                    names = [str(entry.get("name") or "未命名") for entry in entries]
                    text = "\n".join(name[:8] for name in names[:3])
                    if len(names) > 3:
                        text += "\n…"
                    button.setText(text)
                    button.setObjectName("cell")
                    color = lesson_color(names[0], self._dark_theme())
                    button.setStyleSheet("border-left:3px solid %s;" % color)
                    rooms = [str(entry.get("room") or "") for entry in entries if entry.get("room")]
                    if rooms:
                        button.setToolTip("、".join(rooms))
                else:
                    button.setText("＋")
                    button.setObjectName("cellEmpty")
                button.setEnabled(self._enabled)
                button.clicked.connect(lambda checked=False, d=day, p=period: self._open_cell(d, p))
                self.grid.addWidget(button, period + 1, day + 1)

    def _dark_theme(self):
        window = self.window()
        return bool(getattr(window, "_dark", False))

    def _open_cell(self, day, period):
        dialog = CellDialog(self, self._plan_entries, day, period, self._periods(),
                            self._cell_changed)
        dialog.exec()
        self._rebuild_grid()

    def _cell_changed(self):
        self.dirty = True
        self._update_status()

    def _on_plan_changed(self, name):
        if self._loading or not name:
            return
        plans = self.state.setdefault("plans", {})
        if name not in plans:
            return
        self.state["active"] = name
        self._plan_entries = plans.setdefault(name, [])
        self.dirty = True
        self._rebuild_grid()
        self._update_status()

    def _new_plan(self):
        text, ok = QInputDialog.getText(self, "新建方案", "方案名称：")
        name = str(text or "").strip()
        if not ok or not name:
            return
        plans = self.state.setdefault("plans", {})
        if name in plans:
            QMessageBox.information(self, "方案", "该方案已存在")
            return
        plans[name] = []
        self.state["active"] = name
        self._loading = True
        self.cmb_plan.addItem(name)
        self.cmb_plan.setCurrentIndex(self.cmb_plan.findText(name))
        self._loading = False
        self._plan_entries = plans[name]
        self.dirty = True
        self._rebuild_grid()
        self._update_status()

    def _rename_plan(self):
        current = str(self.cmb_plan.currentText() or "")
        plans = self.state.get("plans") or {}
        if not current or current not in plans:
            return
        text, ok = QInputDialog.getText(self, "重命名方案", "方案名称：", text=current)
        name = str(text or "").strip()
        if not ok or not name or name == current:
            return
        if name in plans:
            QMessageBox.information(self, "方案", "该方案已存在")
            return
        plans[name] = plans.pop(current)
        self.state["active"] = name
        self._loading = True
        index = self.cmb_plan.currentIndex()
        self.cmb_plan.setItemText(index, name)
        self._loading = False
        self.dirty = True
        self._update_status()

    def _delete_plan(self):
        current = str(self.cmb_plan.currentText() or "")
        plans = self.state.get("plans") or {}
        if not current or current not in plans:
            return
        if len(plans) <= 1:
            QMessageBox.information(self, "方案", "至少保留一个方案")
            return
        if QMessageBox.question(self, "删除方案", "删除方案「%s」？" % current) != \
                QMessageBox.StandardButton.Yes:
            return
        plans.pop(current, None)
        name = sorted(plans.keys())[0]
        self.state["active"] = name
        self._plan_entries = plans.setdefault(name, [])
        self._loading = True
        self.cmb_plan.clear()
        for item in sorted(plans.keys()):
            self.cmb_plan.addItem(item)
        self.cmb_plan.setCurrentIndex(max(0, self.cmb_plan.findText(name)))
        self._loading = False
        self.dirty = True
        self._rebuild_grid()
        self._update_status()

    def _edit_periods(self):
        dialog = PeriodsDialog(self, self._periods())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.state["periods"] = dialog.result_periods()
        self.dirty = True
        self._rebuild_grid()
        self._update_status()

    def _edit_semester(self):
        dialog = SemesterDialog(self, str(self.state.get("semester_start") or ""),
                                str(self.state.get("week_mode") or "auto"))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        start, mode = dialog.result_values()
        self.state["semester_start"] = start
        self.state["week_mode"] = mode
        self.dirty = True
        self._update_status()

    def _refresh(self):
        if self.dirty:
            if QMessageBox.question(self, "刷新", "本地有未保存的修改，刷新会丢弃这些修改，继续？") != \
                    QMessageBox.StandardButton.Yes:
                return
            self.dirty = False
        self.lbl_status.setText("正在刷新…")
        if self.on_refresh is not None:
            self.on_refresh()

    def _save(self):
        if self.on_save is None:
            self.lbl_status.setText("尚未连接电脑端")
            return
        self.lbl_status.setText("正在保存…")
        self.on_save()

    def save_force(self):
        if self.on_save_force is None:
            return
        self.lbl_status.setText("正在覆盖…")
        self.on_save_force()

    def show_status(self, text):
        self.lbl_status.setText(str(text or ""))

    def mark_saved(self, rev):
        self.rev = str(rev or "")
        self.dirty = False
        self._update_status()

    def set_enabled(self, enabled):
        self._enabled = bool(enabled)
        self.btn_refresh.setEnabled(self._enabled)
        self.btn_save.setEnabled(self._enabled)
        self._rebuild_grid()

    def refresh_theme(self):
        self._rebuild_grid()

    def _update_status(self):
        if self.dirty:
            self.lbl_status.setText("已修改，未保存")
        elif self.rev:
            self.lbl_status.setText("已同步 · 修订 %s" % self.rev)
        else:
            self.lbl_status.setText("尚未同步")


class NotifyPage(QWidget):
    def __init__(self, config, on_send, parent=None):
        super().__init__(parent)
        self.config = config
        self.on_send = on_send
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        card = QFrame(self)
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(9)
        form.addWidget(_label("教师通知", bold=True))
        form.addWidget(_label("教师通知会强制置顶于所有窗口之上。", dim=True))
        self.edit_title = QLineEdit(card)
        self.edit_title.setPlaceholderText("通知标题，例如：下午第三节课调整")
        form.addWidget(self.edit_title)
        self.edit_body = QTextEdit(card)
        self.edit_body.setPlaceholderText("通知内容")
        self.edit_body.setMinimumHeight(130)
        form.addWidget(self.edit_body)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("显示时长", card))
        self.spin_duration = QSpinBox(card)
        self.spin_duration.setRange(3, 30)
        self.spin_duration.setValue(8)
        self.spin_duration.setSuffix(" 秒")
        row.addWidget(self.spin_duration)
        row.addStretch(1)
        self.btn_send = QPushButton("发送教师通知", card)
        self.btn_send.setObjectName("primary")
        self.btn_send.clicked.connect(self._send)
        row.addWidget(self.btn_send)
        form.addLayout(row)
        self.lbl_status = _label("", dim=True)
        form.addWidget(self.lbl_status)
        layout.addWidget(card)
        layout.addWidget(_label("最近发送", bold=True))
        self.list_history = QListWidget(self)
        layout.addWidget(self.list_history, 1)

    def _send(self):
        title = self.edit_title.text().strip()
        body = self.edit_body.toPlainText().strip()
        if not title and not body:
            self.lbl_status.setText("请填写标题或内容")
            return
        self.lbl_status.setText("正在发送…")
        if self.on_send is not None:
            self.on_send(title or "教师通知", body, int(self.spin_duration.value()))

    def on_result(self, ok, message):
        if ok:
            self.lbl_status.setText("教师通知已发送")
        else:
            self.lbl_status.setText(message or "发送失败")

    def set_enabled(self, enabled):
        self.btn_send.setEnabled(bool(enabled))

    def set_history(self, rows):
        self.list_history.clear()
        if not rows:
            self.list_history.addItem("暂无记录")
            return
        for item in rows:
            stamp = int(item.get("ts") or 0)
            title = str(item.get("title") or item.get("body") or "教师通知")
            when = time.strftime("%m-%d %H:%M", time.localtime(stamp)) if stamp else ""
            self.list_history.addItem("%s · 教师通知 · %s" % (when, title))


class DevicePage(QWidget):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.session = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        card = QFrame(self)
        card.setObjectName("card")
        form = QVBoxLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(8)
        form.addWidget(_label("设备信息", bold=True))
        self.lbl_host = _label("主机：—")
        self.lbl_address = _label("地址：—", dim=True)
        self.lbl_state = _label("状态：未连接", dim=True)
        self.lbl_version = _label("ZX 版本：—", dim=True)
        form.addWidget(self.lbl_host)
        form.addWidget(self.lbl_address)
        form.addWidget(self.lbl_state)
        form.addWidget(self.lbl_version)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_reconnect = QPushButton("重新连接", card)
        self.btn_reconnect.clicked.connect(self._reconnect)
        row.addWidget(self.btn_reconnect)
        self.btn_unpair = QPushButton("解除配对", card)
        self.btn_unpair.setObjectName("danger")
        self.btn_unpair.clicked.connect(self._unpair)
        row.addWidget(self.btn_unpair)
        self.btn_remove = QPushButton("移除设备", card)
        self.btn_remove.setObjectName("danger")
        self.btn_remove.clicked.connect(self._remove)
        row.addWidget(self.btn_remove)
        row.addStretch(1)
        form.addLayout(row)
        layout.addWidget(card)
        alias_card = QFrame(self)
        alias_card.setObjectName("card")
        alias_form = QVBoxLayout(alias_card)
        alias_form.setContentsMargins(18, 16, 18, 16)
        alias_form.setSpacing(6)
        alias_form.addWidget(_label("本机备注", bold=True))
        alias_form.addWidget(_label("只保存在电脑上，用于区分多台设备。", dim=True))
        self.edit_alias = QLineEdit(alias_card)
        self.edit_alias.setPlaceholderText("例如：高一(1)班电脑")
        alias_form.addWidget(self.edit_alias)
        save_alias = QPushButton("保存备注", alias_card)
        save_alias.clicked.connect(self._save_alias)
        alias_form.addWidget(save_alias)
        layout.addWidget(alias_card)
        help_card = QFrame(self)
        help_card.setObjectName("card")
        help_form = QVBoxLayout(help_card)
        help_form.setContentsMargins(18, 16, 18, 16)
        help_form.setSpacing(4)
        help_form.addWidget(_label("说明", bold=True))
        help_form.addWidget(_label("解除配对会通知电脑端移除本机；移除设备只删除本地的记录。", dim=True))
        help_form.addWidget(_label("连接失败时，请确认电脑端 ZX 已启用远程控制。", dim=True))
        layout.addWidget(help_card)
        layout.addStretch(1)

    def set_session(self, session):
        self.session = session
        if session is None:
            return
        self.lbl_host.setText("主机：%s" % session.display_name())
        self.lbl_address.setText("地址：%s:%d" % (session.address, session.port))
        self.lbl_state.setText("状态：%s" % session.status)
        self.lbl_version.setText("ZX 版本：%s" % (session.host_version or "—"))
        self.edit_alias.setText(session.alias)
        self.btn_unpair.setEnabled(session.is_connected())

    def _reconnect(self):
        if self.session is not None:
            self.callback.reconnect(self.session)

    def _unpair(self):
        if self.session is not None:
            self.callback.unpair(self.session)

    def _remove(self):
        if self.session is not None:
            self.callback.remove(self.session)

    def _save_alias(self):
        if self.session is not None:
            self.callback.alias(self.session, self.edit_alias.text())




class ConnectPage(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._items = []
        self.window = parent
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 26, 40, 30)
        layout.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(_label(APP_NAME, bold=True))
        top.addStretch(1)
        self.btn_settings = QPushButton("设置", self)
        self.btn_settings.setObjectName("small")
        top.addWidget(self.btn_settings)
        layout.addLayout(top)
        title = _label("添加设备", bold=True)
        title.setObjectName("title")
        layout.addWidget(title)
        layout.addWidget(_label("在 ZX 设置页“远程”中启用并生成配对码，然后在这里连接。", dim=True))
        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(QLabel("设备名称"))
        self.edit_name = QLineEdit(str(config.data.get("device_name") or ""), self)
        self.edit_name.editingFinished.connect(self._save_name)
        name_row.addWidget(self.edit_name, 1)
        layout.addLayout(name_row)
        self.list_hosts = QListWidget(self)
        self.list_hosts.itemDoubleClicked.connect(lambda item: self._connect())
        layout.addWidget(self.list_hosts, 1)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.btn_scan = QPushButton("扫描局域网", self)
        row.addWidget(self.btn_scan)
        self.btn_connect = QPushButton("连接选中", self)
        self.btn_connect.setObjectName("primary")
        self.btn_connect.clicked.connect(self._connect)
        row.addWidget(self.btn_connect)
        self.lbl_status = _label("准备扫描", dim=True)
        row.addWidget(self.lbl_status, 1)
        layout.addLayout(row)
        manual = QHBoxLayout()
        manual.setSpacing(8)
        manual.addWidget(QLabel("手动地址"))
        self.edit_manual = QLineEdit(self)
        self.edit_manual.setPlaceholderText("例如 192.168.1.5:48700")
        manual.addWidget(self.edit_manual, 1)
        self.btn_manual = QPushButton("连接", self)
        manual.addWidget(self.btn_manual)
        layout.addLayout(manual)
        layout.addWidget(_label("配对码 5 分钟内有效，每台设备只需配对一次。可同时配对多台电脑。", dim=True))

    def _save_name(self):
        name = self.edit_name.text().strip() or "Windows 电脑"
        self.config.data["device_name"] = name
        self.config.save()

    def device_name(self):
        self._save_name()
        return self.config.data.get("device_name") or "Windows 电脑"

    def set_status(self, text):
        self.lbl_status.setText(str(text))

    def set_hosts(self, discovered, sessions):
        self.list_hosts.clear()
        self._items = []
        known = set()
        for session in sessions:
            if not session.host_id or not session.token:
                continue
            known.add(session.host_id)
            row = {"mode": "saved", "session": session, "address": session.address,
                   "port": session.port}
            text = "%s · 已配对 · %s:%d · %s" % (session.display_name(), session.address,
                                                 session.port, session.status)
            self._add_row(text, row)
        for host, address, port in discovered:
            hid = str((host or {}).get("id") or "")
            if hid in known:
                continue
            row = {"mode": "new", "host": host, "address": address, "port": int(port)}
            text = "%s · 未配对 · %s:%d" % ((host or {}).get("name") or "ZX", address, port)
            self._add_row(text, row)
        if not self._items:
            item = QListWidgetItem("暂未发现设备，可点击“扫描局域网”或手动输入地址")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_hosts.addItem(item)

    def _add_row(self, text, row):
        item = QListWidgetItem(text)
        self.list_hosts.addItem(item)
        self._items.append(row)

    def selected(self):
        index = self.list_hosts.currentRow()
        if index < 0 or index >= len(self._items):
            return None
        return self._items[index]

    def _connect(self):
        if self.window is not None:
            self.window.connect_selected()


class HomePage(QWidget):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self.callback = callback
        self.sessions = []
        self.selected = set()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(8)
        top = QHBoxLayout()
        top.addWidget(_label(APP_NAME, bold=True))
        top.addStretch(1)
        settings = QPushButton("设置")
        settings.clicked.connect(self.callback.settings)
        top.addWidget(settings)
        add = QPushButton("+")
        add.clicked.connect(self.callback.add_device)
        top.addWidget(add)
        layout.addLayout(top)
        self.lbl_sub = _label("", dim=True)
        layout.addWidget(self.lbl_sub)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        self.holder = QWidget(scroll)
        self.rows = QVBoxLayout(self.holder)
        self.rows.setContentsMargins(0, 4, 0, 4)
        self.rows.setSpacing(7)
        scroll.setWidget(self.holder)
        layout.addWidget(scroll, 1)
        self.btn_group = QPushButton("发送教师通知（已选 0 台）")
        self.btn_group.setObjectName("primary")
        self.btn_group.clicked.connect(self._group)
        layout.addWidget(self.btn_group)

    def set_sessions(self, sessions):
        self.sessions = list(sessions or [])
        keys = {session.key() for session in self.sessions}
        self.selected &= keys
        self._rebuild()

    def _rebuild(self):
        while self.rows.count():
            item = self.rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.lbl_sub.setText("设备主页 · 已配对 %d 台" % len(self.sessions))
        if not self.sessions:
            card = QFrame(self.holder)
            card.setObjectName("card")
            form = QVBoxLayout(card)
            form.setContentsMargins(18, 16, 18, 16)
            form.addWidget(_label("还没有配对设备", bold=True))
            form.addWidget(_label("点击右上角“+”扫描局域网或手动输入电脑地址。", dim=True))
            add = QPushButton("添加设备", card)
            add.setObjectName("primary")
            add.clicked.connect(self.callback.add_device)
            form.addWidget(add)
            self.rows.addWidget(card)
            self.rows.addStretch(1)
            self._update_group()
            return
        for session in self.sessions:
            row = QHBoxLayout()
            check = QCheckBox(self.holder)
            check.setEnabled(session.is_connected())
            check.setChecked(session.key() in self.selected)
            check.toggled.connect(lambda checked, s=session: self._toggle(s, checked))
            row.addWidget(check)
            button = QPushButton(self.holder)
            button.setObjectName("cell")
            button.setText("%s\n%s:%d · %s" % (session.display_name(), session.address,
                                               session.port, session.status))
            button.setStyleSheet("text-align:left; padding:10px;")
            button.clicked.connect(lambda checked=False, s=session: self.callback.open_device(s))
            row.addWidget(button, 1)
            holder = QWidget(self.holder)
            holder.setLayout(row)
            holder.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            self.rows.addWidget(holder)
        self.rows.addStretch(1)
        self._update_group()

    def _toggle(self, session, checked):
        if checked:
            self.selected.add(session.key())
        else:
            self.selected.discard(session.key())
        self._update_group()

    def _update_group(self):
        targets = self._targets()
        self.btn_group.setText("发送教师通知（已选 %d 台）" % len(targets))
        self.btn_group.setEnabled(bool(targets))

    def _targets(self):
        return [session for session in self.sessions
                if session.is_connected() and session.key() in self.selected]

    def _group(self):
        targets = self._targets()
        if targets:
            self.callback.group_notify(targets)


class GroupNotifyDialog(QDialog):
    def __init__(self, parent, targets, on_send):
        super().__init__(parent)
        self.on_send = on_send
        self.setWindowTitle("发送教师通知")
        self.resize(480, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        names = "、".join(session.display_name() for session in targets)
        layout.addWidget(_label("发送到 %d 台设备：%s" % (len(targets), names), dim=True))
        self.edit_title = QLineEdit(self)
        self.edit_title.setPlaceholderText("通知标题")
        self.edit_body = QTextEdit(self)
        self.edit_body.setPlaceholderText("通知内容")
        self.edit_body.setMinimumHeight(120)
        self.spin_duration = QSpinBox(self)
        self.spin_duration.setRange(3, 30)
        self.spin_duration.setValue(8)
        self.spin_duration.setSuffix(" 秒")
        form = QFormLayout()
        form.addRow("标题", self.edit_title)
        form.addRow("内容", self.edit_body)
        form.addRow("显示时长", self.spin_duration)
        layout.addLayout(form)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                               QDialogButtonBox.StandardButton.Ok, self)
        box.button(QDialogButtonBox.StandardButton.Ok).setText("发送")
        box.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        box.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        box.accepted.connect(self._accept)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _accept(self):
        title = self.edit_title.text().strip()
        body = self.edit_body.toPlainText().strip()
        if not title and not body:
            QMessageBox.warning(self, "教师通知", "请填写标题或内容")
            return
        if self.on_send is not None:
            self.on_send(title or "教师通知", body, int(self.spin_duration.value()))
        super().accept()


class SettingsDialog(QDialog):
    def __init__(self, config, manager, on_theme, dark, parent=None):
        super().__init__(parent)
        self.config = config
        self.manager = manager
        self.on_theme = on_theme
        self.dark = dark
        self.setWindowTitle("设置")
        self.resize(480, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(9)
        layout.addWidget(_label("%s v%s · 构建 %s" % (APP_NAME, VERSION, BUILD_VERSION),
                                dim=True))
        layout.addWidget(_label("外观", bold=True))
        self.cmb_theme = QComboBox(self)
        self.cmb_theme.addItem("跟随系统", "system")
        self.cmb_theme.addItem("深色", "dark")
        self.cmb_theme.addItem("浅色", "light")
        mode = str(config.data.get("theme") or "system")
        self.cmb_theme.setCurrentIndex(max(0, self.cmb_theme.findData(mode)))
        self.cmb_theme.currentIndexChanged.connect(
            lambda index: self.on_theme(str(self.cmb_theme.itemData(index))))
        layout.addWidget(self.cmb_theme)
        layout.addWidget(_label("项目主页", bold=True))
        for name, url in (("Gitee", "https://gitee.com/guzhi233/countdown---djs"),
                          ("GitHub", "https://github.com/GuZhi-233/Countdown-DJS")):
            link = QPushButton("%s · %s" % (name, url), self)
            link.setFlat(True)
            link.setStyleSheet("text-align:left; color:%s;" %
                               ("#FBBF24" if self.dark else "#C2410C"))
            link.clicked.connect(
                lambda checked=False, target=url: QDesktopServices.openUrl(QUrl(target)))
            layout.addWidget(link)
        layout.addWidget(_label("使用说明", bold=True))
        layout.addWidget(_label("1. 电脑端 ZX 设置页“远程”中启用并生成配对码。", dim=True))
        layout.addWidget(_label("2. 在“添加设备”中扫描或手动输入地址并完成配对。", dim=True))
        layout.addWidget(_label("3. 已配对设备会出现在主页，启动时自动尝试连接。", dim=True))
        layout.addWidget(_label("4. 主页勾选多台可群发教师通知，进入详情可单独发送。", dim=True))
        self.lbl_count = _label("已配对设备：%d 台" % len(manager.sessions), dim=True)
        layout.addWidget(self.lbl_count)
        clean = QPushButton("清理失效配对", self)
        clean.clicked.connect(self._clean)
        layout.addWidget(clean)
        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        box.button(QDialogButtonBox.StandardButton.Close).setText("关闭")
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _clean(self):
        removed = self.manager.remove_invalid()
        self.lbl_count.setText("已配对设备：%d 台" % len(self.manager.sessions))
        QMessageBox.information(self, "清理失效配对",
                                "已清理 %d 台" % removed if removed else "没有失效配对")


class DeviceDetailPage(QWidget):
    def __init__(self, config, callback, parent=None):
        super().__init__(parent)
        self.config = config
        self.callback = callback
        self.session = None
        self.last_title = "教师通知"
        self.dark = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        top = QHBoxLayout()
        back = QPushButton("‹")
        back.setFixedWidth(38)
        back.clicked.connect(self.callback.back)
        top.addWidget(back)
        box = QVBoxLayout()
        self.lbl_host = _label("设备", bold=True)
        self.lbl_state = _label("未连接", dim=True)
        box.addWidget(self.lbl_host)
        box.addWidget(self.lbl_state)
        top.addLayout(box, 1)
        settings = QPushButton("设置")
        settings.clicked.connect(self.callback.settings)
        top.addWidget(settings)
        layout.addLayout(top)
        tabs = QHBoxLayout()
        self.tab_buttons = []
        for index, name in enumerate(("课表", "教师通知", "设备")):
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, value=index: self.show_tab(value))
            tabs.addWidget(button)
            self.tab_buttons.append(button)
        layout.addLayout(tabs)
        self.stack = QStackedWidget(self)
        self.schedule = SchedulePage(self.stack)
        self.schedule.on_save = lambda: self._save(False)
        self.schedule.on_save_force = lambda: self._save(True)
        self.schedule.on_refresh = self._refresh
        self.notify = NotifyPage(config, self._send_notify, self.stack)
        self.device = DevicePage(self, self.stack)
        self.stack.addWidget(self.schedule)
        self.stack.addWidget(self.notify)
        self.stack.addWidget(self.device)
        layout.addWidget(self.stack, 1)
        self.show_tab(0)

    def set_session(self, session):
        self.session = session
        if session is None:
            return
        self.lbl_host.setText(session.display_name())
        self.lbl_state.setText(session.status)
        self.schedule.setEnabled(session.is_connected())
        if not self.schedule.dirty:
            self.schedule.load_state(session.state, session.rev, True)
        self.notify.set_enabled(session.is_connected())
        self.notify.set_history(self._history())
        self.device.set_session(session)

    def on_session_changed(self, session):
        if session is not self.session:
            return
        self.lbl_host.setText(session.display_name())
        self.lbl_state.setText(session.status)
        self.schedule.setEnabled(session.is_connected())
        self.notify.set_enabled(session.is_connected())
        self.device.set_session(session)

    def on_state_changed(self, session):
        if session is not self.session:
            return
        if self.schedule.dirty:
            self.schedule.lbl_status.setText("电脑端课表已更新，保存前请先刷新")
            return
        self.schedule.load_state(session.state, session.rev, True)
        self.lbl_state.setText(session.status)
        self.schedule.setEnabled(session.is_connected())
        self.notify.set_enabled(session.is_connected())

    def on_saved(self, session, rev):
        if session is not self.session:
            return
        self.schedule.mark_saved(rev)
        self.schedule.show_status("已保存到 ZX")

    def on_conflict(self, session, state, rev, message):
        if session is not self.session:
            return
        box = QMessageBox(self)
        box.setWindowTitle("课表冲突")
        box.setText(message or "电脑端课表已变化")
        box.setInformativeText("重新加载会丢弃本地修改；覆盖会以本地版本替换电脑端课表。")
        reload_btn = box.addButton("重新加载", QMessageBox.ButtonRole.AcceptRole)
        overwrite_btn = box.addButton("覆盖电脑端", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("取消", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is reload_btn:
            self.schedule.dirty = False
            session.request_schedule()
        elif box.clickedButton() is overwrite_btn:
            self.schedule.dirty = False
            session.save_schedule(self.schedule.state, self.schedule.rev, True)
            self.schedule.show_status("正在覆盖…")

    def on_notify_result(self, session, ok, message):
        if session is not self.session:
            return
        self.notify.on_result(ok, message)
        if ok:
            history = self.config.data.setdefault("history", [])
            history.insert(0, {"ts": int(time.time()), "mode": "quick",
                               "title": self.last_title, "hostId": session.host_id,
                               "hostName": session.display_name()})
            self.config.data["history"] = history[:50]
            self.config.save()
            self.notify.set_history(self._history())

    def on_remote_changed(self, session, rev):
        if session is not self.session:
            return
        if self.schedule.dirty:
            self.schedule.lbl_status.setText("电脑端课表已更新，保存前请先刷新")
            return
        if rev != self.schedule.rev:
            session.request_schedule()

    def show_tab(self, index):
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.tab_buttons):
            if position == index:
                button.setStyleSheet("color:%s; font-weight:bold;" %
                                     ("#FBBF24" if self.dark else "#C2410C"))
            else:
                button.setStyleSheet("")

    def _save(self, force):
        if self.session is None:
            return
        self.session.save_schedule(self.schedule.state, self.schedule.rev, force)
        self.schedule.show_status("正在覆盖…" if force else "正在保存…")

    def _refresh(self):
        if self.session is not None:
            self.session.request_schedule()

    def _send_notify(self, title, body, duration):
        if self.session is None or not self.session.is_connected():
            self.notify.on_result(False, "尚未连接电脑端")
            return
        self.last_title = title
        self.session.send_notify(title, body, duration)

    def _history(self):
        if self.session is None:
            return []
        return [row for row in self.config.data.get("history") or []
                if str(row.get("hostId") or "") == self.session.host_id]

    def reconnect(self, session):
        self.callback.reconnect(session)

    def unpair(self, session):
        self.callback.unpair(session)

    def remove(self, session):
        self.callback.remove(session)

    def alias(self, session, alias):
        self.callback.alias(session, alias)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = Config()
        self._dark = is_system_dark()
        self.discovered = []
        self.detail_pages = {}
        self.current_detail = None
        self.group_pending = {}
        self.group_ok = 0
        self.group_fail = 0
        self.setWindowTitle(APP_NAME)
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)
        central = QWidget(self)
        central.setObjectName("zxRoot")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        self.pages = QStackedWidget(central)
        layout.addWidget(self.pages)
        self.connect_page = ConnectPage(self.config, self)
        self.home_page = HomePage(self, self)
        self.detail_holder = QWidget(self)
        self.detail_layout = QVBoxLayout(self.detail_holder)
        self.detail_layout.setContentsMargins(0, 0, 0, 0)
        self.pages.addWidget(self.connect_page)
        self.pages.addWidget(self.home_page)
        self.pages.addWidget(self.detail_holder)
        self.manager = DeviceManager(self.config, self)
        self.manager.sessions_changed.connect(self._on_sessions_changed)
        self.manager.session_changed.connect(self._on_session_changed)
        self.manager.paired.connect(self._on_paired)
        self.manager.state_changed.connect(self._on_state_changed)
        self.manager.saved.connect(self._on_saved)
        self.manager.conflict.connect(self._on_conflict)
        self.manager.notify_result.connect(self._on_notify_result)
        self.manager.failed.connect(self._on_failed)
        self.manager.remote_changed.connect(self._on_remote_changed)
        self.connect_page.btn_scan.clicked.connect(self.scan)
        self.connect_page.btn_manual.clicked.connect(self.connect_manual)
        self.connect_page.btn_settings.clicked.connect(self.show_settings)
        self.discovery = Discovery(self)
        self.discovery.found.connect(self._on_found)
        self.discovery.finished.connect(self._on_scan_finished)
        self.discovery.error.connect(self._on_scan_error)
        self.apply_theme()
        if self.manager.sessions:
            self.show_home()
            self.manager.connect_all()
        else:
            self.show_connect()
        QTimer.singleShot(250, self.scan)

    def apply_theme(self):
        mode = str(self.config.data.get("theme") or "system")
        if mode == "dark":
            self._dark = True
        elif mode == "light":
            self._dark = False
        else:
            self._dark = is_system_dark()
        self.setStyleSheet(qss(self._dark))
        if self.current_detail is not None:
            self.current_detail.schedule.refresh_theme()
        for page in self.detail_pages.values():
            page.dark = self._dark
            page.show_tab(page.stack.currentIndex())
        self.home_page.set_sessions(self.manager.sessions)

    def scan(self):
        self.discovered = []
        self.connect_page.set_status("正在扫描局域网…")
        self.discovery.scan()

    def _on_found(self, host, address, port):
        self.discovered.append((host, address, port))

    def _on_scan_finished(self):
        self.connect_page.set_hosts(self.discovered, self.manager.sessions)
        self.connect_page.set_status("扫描完成，发现 %d 台设备" % len(self.connect_page._items))

    def _on_scan_error(self, message):
        self.connect_page.set_status(str(message))

    def connect_selected(self):
        row = self.connect_page.selected()
        if row is None:
            self.connect_page.set_status("请先选择一个设备")
            return
        if row.get("mode") == "saved":
            session = row.get("session")
            if session is not None:
                session.connect_to()
                self.show_home()
            return
        self._pair_new(row.get("host") or {}, row.get("address"), row.get("port"))

    def connect_manual(self):
        text = self.connect_page.edit_manual.text().strip()
        if not text:
            self.connect_page.set_status("请输入地址")
            return
        address = text
        port = DEFAULT_CONTROL_PORT
        if ":" in text:
            head, tail = text.rsplit(":", 1)
            try:
                port = int(tail)
                address = head
            except Exception:
                self.connect_page.set_status("地址格式应为 IP:端口")
                return
        self._pair_new({"name": "手动连接"}, address, port)

    def _pair_new(self, host, address, port):
        dialog = PairDialog(self, str(host.get("name") or "ZX"),
                            "%s:%d" % (address, port), self.connect_page.device_name())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        code, device_name = dialog.values()
        self.config.data["device_name"] = device_name
        self.config.save()
        self.manager.pair_new(address, port, code)
        self.show_home()

    def show_connect(self):
        self.pages.setCurrentWidget(self.connect_page)
        self.current_detail = None
        self.connect_page.set_hosts(self.discovered, self.manager.sessions)

    def show_home(self):
        self.pages.setCurrentWidget(self.home_page)
        self.current_detail = None
        self.home_page.set_sessions(self.manager.sessions)

    def open_detail(self, session):
        page = self.detail_pages.get(session.key())
        if page is None:
            page = DeviceDetailPage(self.config, self, self.detail_holder)
            self.detail_pages[session.key()] = page
            self.detail_layout.addWidget(page)
        page.dark = self._dark
        page.show_tab(page.stack.currentIndex())
        for index in range(self.detail_layout.count()):
            widget = self.detail_layout.itemAt(index).widget()
            if widget is not None:
                widget.setVisible(widget is page)
        self.current_detail = page
        page.set_session(session)
        self.pages.setCurrentWidget(self.detail_holder)

    def _close_detail(self, session):
        page = self.detail_pages.pop(session.key(), None)
        if page is not None:
            self.detail_layout.removeWidget(page)
            page.deleteLater()
        if self.current_detail is page:
            self.current_detail = None

    def show_settings(self):
        SettingsDialog(self.config, self.manager, self.set_theme, self._dark, self).exec()

    def set_theme(self, mode):
        self.config.data["theme"] = str(mode or "system")
        self.config.save()
        self.apply_theme()

    def start_group_notify(self, targets):
        GroupNotifyDialog(self, targets,
                          lambda title, body, duration: self._send_group(targets, title,
                                                                        body, duration)).exec()

    def _send_group(self, targets, title, body, duration):
        self.group_pending = {session.key(): False for session in targets}
        self.group_ok = 0
        self.group_fail = 0
        for session in targets:
            session.send_notify(title, body, duration)
        self.statusBar().showMessage("正在发送到 %d 台设备…" % len(targets), 4000)
        QTimer.singleShot(6000, self._group_timeout)

    def _group_timeout(self):
        if self.group_pending:
            pending = len(self.group_pending)
            self.group_pending.clear()
            self.statusBar().showMessage("部分设备未响应：%d 台" % pending, 5000)

    def _on_sessions_changed(self):
        self.home_page.set_sessions(self.manager.sessions)
        self.connect_page.set_hosts(self.discovered, self.manager.sessions)
        if self.current_detail is not None:
            session = self.current_detail.session
            if session is not None and self.manager.find(session.host_id) is None:
                self.show_home()

    def _on_session_changed(self, session):
        self.home_page.set_sessions(self.manager.sessions)
        if self.current_detail is not None:
            self.current_detail.on_session_changed(session)
        self.connect_page.set_hosts(self.discovered, self.manager.sessions)

    def _on_paired(self, session):
        self.show_home()
        self.statusBar().showMessage("配对成功：%s" % session.display_name(), 5000)

    def _on_state_changed(self, session):
        if self.current_detail is not None:
            self.current_detail.on_state_changed(session)

    def _on_saved(self, session, rev):
        if self.current_detail is not None:
            self.current_detail.on_saved(session, rev)
        self.statusBar().showMessage("课表已保存到 %s" % session.display_name(), 5000)

    def _on_conflict(self, session, state, rev, message):
        if self.current_detail is not None:
            self.current_detail.on_conflict(session, state, rev, message)

    def _on_notify_result(self, session, ok, message):
        if self.current_detail is not None:
            self.current_detail.on_notify_result(session, ok, message)
        if session.key() in self.group_pending:
            self.group_pending.pop(session.key(), None)
            if ok:
                self.group_ok += 1
            else:
                self.group_fail += 1
            if not self.group_pending:
                self.statusBar().showMessage("发送完成：成功 %d 台，失败 %d 台"
                                             % (self.group_ok, self.group_fail), 6000)

    def _on_failed(self, session, message):
        self.connect_page.set_status(message)
        self.statusBar().showMessage(message, 5000)
        if self.pages.currentWidget() is self.detail_holder:
            QMessageBox.warning(self, "连接失败", message)
        if not self.manager.sessions:
            self.show_connect()

    def _on_remote_changed(self, session, rev):
        if self.current_detail is not None:
            self.current_detail.on_remote_changed(session, rev)
        else:
            session.request_schedule()

    def reconnect(self, session):
        session.connect_to()

    def unpair(self, session):
        if QMessageBox.question(self, "解除配对", "解除后需要重新输入配对码，继续？") != \
                QMessageBox.StandardButton.Yes:
            return
        session.unpair()
        QTimer.singleShot(400, lambda: self._remove_session(session))

    def remove_session(self, session):
        if QMessageBox.question(self, "移除设备", "移除设备只删除本地记录，继续？") != \
                QMessageBox.StandardButton.Yes:
            return
        self._remove_session(session)

    def remove(self, session):
        self.remove_session(session)

    def _remove_session(self, session):
        self._close_detail(session)
        self.manager.remove(session)
        self.show_home()

    def alias(self, session, alias):
        session.set_alias(alias)
        self.statusBar().showMessage("备注已保存", 3000)

    def back(self):
        self.show_home()

    def add_device(self):
        self.show_connect()

    def settings(self):
        self.show_settings()

    def group_notify(self, targets):
        self.start_group_notify(targets)

    def closeEvent(self, event):
        self.manager.close_all()
        self.discovery.stop()
        self.config.save()
        super().closeEvent(event)

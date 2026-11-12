from PyQt6.QtGui import QGuiApplication


def is_system_dark():
    try:
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme is not None:
            return str(scheme).lower().endswith("dark")
    except Exception:
        pass
    try:
        palette = QGuiApplication.palette()
        return palette.window().color().lightness() < 128
    except Exception:
        return True


def colors(dark):
    if dark:
        return {
            "bg": "#12141C",
            "panel": "#1A1D27",
            "panel2": "#1F2330",
            "input": "#232634",
            "text": "#ECEEF4",
            "dim": "#8B90A0",
            "border": "#3A3F52",
            "accent": "#FBBF24",
            "accent2": "#FCD34D",
            "accent_text": "#12141C",
            "danger": "#F43F5E",
            "success": "#34D399",
            "blue": "#5AA9FF",
            "purple": "#9B7BF0",
        }
    return {
        "bg": "#F4F5F7",
        "panel": "#F3F4F6",
        "panel2": "#EEF0F4",
        "input": "#FFFFFF",
        "text": "#12141C",
        "dim": "#5C6270",
        "border": "#D7DAE0",
        "accent": "#C2410C",
        "accent2": "#D97706",
        "accent_text": "#FFFFFF",
        "danger": "#BE123C",
        "success": "#059669",
        "blue": "#1F6FD0",
        "purple": "#6D4AC7",
    }


def lesson_color(name, dark):
    palette = ("#5AA9FF", "#34D399", "#9B7BF0", "#FBBF24", "#F43F5E", "#22D3EE") if dark else \
              ("#1F6FD0", "#059669", "#6D4AC7", "#D97706", "#E11D48", "#0891B2")
    total = 0
    for char in str(name or ""):
        total += ord(char)
    return palette[total % len(palette)]


def qss(dark):
    c = colors(dark)
    return """
QWidget{font-family:'Microsoft YaHei','Segoe UI';font-size:13px;color:%(text)s;background:transparent;}
QWidget#zxRoot{background:%(bg)s;}
QDialog{background:%(bg)s;}
QLabel{background:transparent;}
QLabel#dim{color:%(dim)s;}
QLabel#title{font-size:20px;font-weight:bold;}
QLabel#sub{color:%(dim)s;}
QPushButton{background:transparent;color:%(text)s;border:1px solid %(border)s;border-radius:7px;padding:6px 13px;}
QPushButton:hover{border-color:%(accent)s;color:%(accent)s;}
QPushButton:pressed{background:%(panel2)s;}
QPushButton:disabled{color:%(dim)s;border-color:%(border)s;}
QPushButton#primary{background:%(accent)s;color:%(accent_text)s;border-color:%(accent)s;font-weight:bold;}
QPushButton#primary:hover{background:%(accent2)s;border-color:%(accent2)s;color:%(accent_text)s;}
QPushButton#danger{color:%(danger)s;border-color:%(danger)s;}
QPushButton#side{text-align:left;border:none;padding:10px 14px;border-radius:8px;}
QPushButton#side:hover{background:%(panel2)s;color:%(text)s;}
QPushButton#side:checked{background:%(panel)s;color:%(accent)s;font-weight:bold;}
QPushButton#cell{background:%(input)s;border:1px solid %(border)s;border-radius:7px;padding:5px;text-align:left;font-size:12px;}
QPushButton#cell:hover{border-color:%(accent)s;}
QPushButton#cellEmpty{background:transparent;border:1px dashed %(border)s;border-radius:7px;color:%(dim)s;font-size:16px;}
QPushButton#cellEmpty:hover{border-color:%(accent)s;color:%(accent)s;}
QLineEdit,QTextEdit,QComboBox,QSpinBox,QDateEdit,QTimeEdit{background:%(input)s;border:1px solid %(border)s;border-radius:6px;padding:5px 9px;color:%(text)s;selection-background-color:%(accent)s;}
QLineEdit:focus,QTextEdit:focus,QComboBox:focus,QSpinBox:focus,QDateEdit:focus,QTimeEdit:focus{border-color:%(accent)s;}
QComboBox::drop-down{border:none;width:18px;}
QComboBox QAbstractItemView{background:%(panel)s;border:1px solid %(border)s;color:%(text)s;selection-background-color:%(accent)s;selection-color:%(accent_text)s;}
QCheckBox{color:%(text)s;spacing:6px;}
QCheckBox::indicator{width:16px;height:16px;border:1px solid %(border)s;border-radius:4px;background:%(input)s;}
QCheckBox::indicator:checked{background:%(accent)s;border-color:%(accent)s;}
QListWidget{background:%(panel)s;border:1px solid %(border)s;border-radius:8px;color:%(text)s;outline:none;}
QListWidget::item{padding:9px 11px;border-radius:6px;margin:2px 4px;}
QListWidget::item:hover{background:%(panel2)s;}
QListWidget::item:selected{background:%(panel2)s;color:%(text)s;border-left:3px solid %(accent)s;}
QFrame#card{background:%(panel)s;border:1px solid %(border)s;border-radius:10px;}
QScrollArea{border:none;background:transparent;}
QScrollBar:vertical{background:transparent;width:8px;margin:0;}
QScrollBar::handle:vertical{background:%(border)s;border-radius:4px;min-height:30px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0px;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QToolTip{background:%(panel)s;color:%(text)s;border:1px solid %(border)s;padding:4px;border-radius:4px;}
""" % c

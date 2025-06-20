# --- START OF FILE study_timer_gui.py ---

import time
import random
import os
import sys
import json
import pygame
import csv # <--- NEW: For writing log files
from datetime import datetime # <--- NEW: For timestamps

# --- PyQt6 Imports ---
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QMessageBox, QSizeGrip
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QSettings
from PyQt6.QtGui import QIcon, QAction

# --- 外部依赖: 全局快捷键 ---
# 请先安装: pip install pynput
try:
    from pynput import keyboard
except ImportError:
    # 在GUI中显示更友好的提示
    def show_pynput_error():
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("缺少关键组件: pynput")
        msg_box.setInformativeText("快捷键功能无法使用。\n请在命令行中运行 'pip install pynput' 来安装它。")
        msg_box.setWindowTitle("依赖缺失")
        msg_box.exec()
    # 稍后在主程序中调用
    keyboard = None


# --- 资源路径函数 ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- 默认配置 ---
DEFAULT_CONFIG = {
    "study_time_min": 3 * 60,
    "study_time_max": 5 * 60,
    "short_break_duration": 10,
    "long_break_threshold": 90 * 60,
    "long_break_duration": 20 * 60,
    "music_folder": "study_music",
    "sound_files": {
        "start_study": "start_study.mp3",
        "start_short_break": "start_short_break.mp3",
        "start_long_break": "start_long_break.mp3",
        "end_long_break": "end_long_break.mp3"
    },
    "total_study_time": 0,
    "hotkeys": {
        "start_resume": "<ctrl>+<alt>+s",
        "pause": "<ctrl>+<alt>+p",
        "reset_cycle": "<ctrl>+<alt>+r"
    }
}

# --- 配置文件加载/创建函数 ---
def load_or_create_config():
    config_path = resource_path('config.json')
    if not os.path.exists(config_path):
        print("未找到 config.json, 正在创建默认配置文件...")
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
            return DEFAULT_CONFIG
        except Exception as e:
            print(f"创建默认配置文件失败: {e}")
            return DEFAULT_CONFIG

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = json.load(f)
            updated = False
            for key, value in DEFAULT_CONFIG.items():
                if key not in user_config:
                    user_config[key] = value
                    updated = True
            if updated:
                print("配置文件已更新，添加了新字段。")
                save_config(user_config)
            return user_config
    except (json.JSONDecodeError, TypeError) as e:
        print(f"警告: 读取 config.json 失败 ({e})。将使用默认配置。")
        return DEFAULT_CONFIG

# --- 配置文件保存函数 ---
def save_config(config_data):
    config_path = resource_path('config.json')
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"错误: 保存配置文件失败: {e}")

# ==============================================================================
# 新增: 学习日志记录器
# ==============================================================================
class StudyLogger:
    def __init__(self, filename="study_log.csv"):
        self.log_path = resource_path(filename)
        self.header = [
            'start_time', 'end_time', 'net_duration_minutes', 'date', 'day_of_week'
        ]
        self._initialize_file()

    def _initialize_file(self):
        """如果日志文件不存在，则创建并写入表头"""
        if not os.path.exists(self.log_path):
            try:
                with open(self.log_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow(self.header)
                print(f"日志文件已创建: {self.log_path}")
            except IOError as e:
                print(f"错误: 无法创建日志文件: {e}")

    def log_session(self, start_time: datetime, end_time: datetime, net_duration_seconds: int):
        """记录一个完整的学习会话"""
        if not all([start_time, end_time, net_duration_seconds > 0]):
            return

        date_str = start_time.strftime('%Y-%m-%d')
        day_of_week = start_time.strftime('%A')
        net_duration_minutes = round(net_duration_seconds / 60, 2)

        row = [
            start_time.strftime('%Y-%m-%d %H:%M:%S'),
            end_time.strftime('%Y-%m-%d %H:%M:%S'),
            net_duration_minutes,
            date_str,
            day_of_week
        ]

        try:
            with open(self.log_path, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(row)
        except IOError as e:
            print(f"错误: 无法写入日志: {e}")


# ==============================================================================
# 核心逻辑层 (已修改)
# ==============================================================================
class StudyTimerLogic(QObject):
    state_changed = pyqtSignal(str, str)
    time_updated = pyqtSignal(int)
    notification_requested = pyqtSignal(str, str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.logger = StudyLogger() # <--- NEW: 初始化日志记录器

        self.is_paused = False
        self.time_remaining_on_pause = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)

        pygame.mixer.init()
        self.sound_paths = self._validate_and_get_sound_paths()
        
        self.total_study_time = self.config.get("total_study_time", 0)

        # --- NEW: 用于追踪单个学习会话的 "临时记事本" ---
        self.current_session_start_time = None
        self.current_session_duration = 0
        
        self.reset_cycle()

    def _clear_current_session(self):
        """清空当前会话的临时记录 (用于重置或中止)"""
        self.current_session_start_time = None
        self.current_session_duration = 0

    def reset_cycle(self):
        self.timer.stop()
        self.cycle_count = 0
        self.current_state = "stopped"
        self.is_paused = False
        self._clear_current_session() # <--- NEW: 放弃未完成的会话
        self.state_changed.emit("沉浸式学习\n右键单击开始", self.current_state)
        self.time_updated.emit(self.total_study_time)

    def reset_all(self):
        self.total_study_time = 0
        self.reset_cycle() # reset_cycle 会调用 clear_session
        self.time_updated.emit(self.total_study_time)
        # 注意: 此处不清除日志文件，用户应手动管理

    def on_timer_timeout(self):
        if self.current_state == "studying":
            # --- 这是关键的 "存档时刻" ---
            if self.current_session_start_time and self.current_session_duration > 0:
                end_time = datetime.now()
                self.logger.log_session(
                    start_time=self.current_session_start_time,
                    end_time=end_time,
                    net_duration_seconds=self.current_session_duration
                )
            self._clear_current_session() # <--- NEW: 记录完成后清空

            study_duration = self.timer.property("duration")
            self.total_study_time += study_duration
            self._run_short_break_cycle()

        elif self.current_state == "short_breaking":
            if self.total_study_time >= self.config["long_break_threshold"]:
                self._run_long_break_cycle()
            else:
                self._run_study_cycle()

        elif self.current_state == "long_breaking":
            self._play_sound("end_long_break")
            self.current_state = "long_break_finished"
            self.state_changed.emit("🎉 长休息结束\n右键开始新征程", self.current_state)
            self.notification_requested.emit("长休息结束", "精力恢复！可以开始下一轮学习了。")

    def _run_study_cycle(self):
        self.cycle_count += 1
        self.current_state = "studying"
        study_duration = random.randint(self.config["study_time_min"], self.config["study_time_max"])
        
        # --- NEW: 在内存中记录新会话的开始 ---
        self.current_session_start_time = datetime.now()
        self.current_session_duration = study_duration

        self.state_changed.emit(f"📚 学习中...\n(第 {self.cycle_count} 轮)", self.current_state)
        self._play_sound("start_study")
        self.timer.setProperty("duration", study_duration)
        self.timer.start(study_duration * 1000)

    # --- 以下方法基本不变 ---
    def load_persistent_time(self, total_study_time):
        self.total_study_time = total_study_time
        self.time_updated.emit(self.total_study_time)

    def _validate_and_get_sound_paths(self):
        folder_path = resource_path(self.config["music_folder"])
        if not os.path.isdir(folder_path): raise FileNotFoundError(f"资源文件夹未找到: {folder_path}")
        paths = {}
        for key, filename in self.config["sound_files"].items():
            path = os.path.join(folder_path, filename)
            if not os.path.isfile(path): raise FileNotFoundError(f"音频文件未找到: {path}")
            paths[key] = path
        return paths

    def _play_sound(self, sound_key):
        sound_path = self.sound_paths.get(sound_key)
        if not sound_path: return
        try:
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
        except pygame.error as e: print(f"播放音频时出错: {e}")

    def start_or_resume(self):
        if self.is_paused: self._resume()
        elif self.current_state in ["stopped", "long_break_finished"]:
            self.is_paused = False
            if self.current_state == "long_break_finished": self.reset_cycle()
            if self.total_study_time >= self.config["long_break_threshold"]:
                self._run_long_break_cycle()
            else:
                self._run_study_cycle()

    def _run_short_break_cycle(self):
        self.current_state = "short_breaking"
        break_duration = self.config["short_break_duration"]
        self.state_changed.emit("☕ 短暂休息中...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_short_break")
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)

    def _run_long_break_cycle(self):
        self.current_state = "long_breaking"
        break_duration = self.config["long_break_duration"]
        self.state_changed.emit("🧘 长时间休息...", self.current_state)
        self.time_updated.emit(self.total_study_time)
        self._play_sound("start_long_break")
        self.timer.setProperty("duration", 0)
        self.timer.start(break_duration * 1000)
    
    def pause(self):
        if self.timer.isActive():
            self.time_remaining_on_pause = self.timer.remainingTime()
            self.timer.stop()
            self.is_paused = True
            self.state_changed.emit("⏸️ 已暂停", self.current_state)

    def _resume(self):
        if self.is_paused:
            self.timer.start(self.time_remaining_on_pause)
            self.is_paused = False
            original_state_text = {
                "studying": f"📚 学习中...\n(第 {self.cycle_count} 轮)",
                "short_breaking": "☕ 短暂休息中...",
                "long_breaking": "🧘 长时间休息..."
            }.get(self.current_state, "未知状态")
            self.state_changed.emit(original_state_text, self.current_state)

    def stop(self):
        self.timer.stop()
        pygame.mixer.quit()

# ==============================================================================
# 快捷键管理器 (无变化)
# ==============================================================================
class HotkeyManager(QObject):
    start_resume_triggered = pyqtSignal()
    pause_triggered = pyqtSignal()
    reset_cycle_triggered = pyqtSignal()

    def __init__(self, hotkey_config, parent=None):
        super().__init__(parent)
        if not keyboard:
            print("警告: pynput 未安装，快捷键功能已禁用。")
            self.listener = None
            return

        self.hotkey_config = hotkey_config
        self.listener = None
        self.hotkey_map = {
            'start_resume': self.start_resume_triggered.emit,
            'pause': self.pause_triggered.emit,
            'reset_cycle': self.reset_cycle_triggered.emit,
        }

    def start(self):
        if not self.listener:
            try:
                pynput_map = {
                    self.hotkey_config[action]: callback
                    for action, callback in self.hotkey_map.items()
                    if action in self.hotkey_config and self.hotkey_config[action]
                }
                if not pynput_map:
                    print("未配置任何有效的快捷键。")
                    return
                
                self.listener = keyboard.GlobalHotKeys(pynput_map)
                self.listener.start()
                print(f"快捷键监听器已启动: {pynput_map.keys()}")
            except Exception as e:
                print(f"启动快捷键监听器失败: {e}. 请检查 config.json 中的快捷键格式。")
                self.listener = None

    def stop(self):
        if self.listener:
            self.listener.stop()
            self.listener = None
            print("快捷键监听器已停止。")

# ==============================================================================
# 图形界面层 (已修改)
# ==============================================================================
class StudyTimerGUI(QWidget):
    def __init__(self, config):
        super().__init__()
        
        self.config = config
        
        try:
            self.logic = StudyTimerLogic(self.config)
        except FileNotFoundError as e:
            QMessageBox.critical(None, "资源错误", f"{e}\n\n请确保所有资源文件都在正确的位置，然后重启程序。")
            self._init_failed = True
            return
        self._init_failed = False
        
        self.dragPos = None
        self.is_locked = False
        
        self.settings = QSettings("MyStudyTimer", "App")
        
        self.is_always_on_top = self.settings.value("ui/alwaysOnTop", True, type=bool)

        self.create_tray_icon()
        
        self.hotkey_manager = HotkeyManager(self.config.get('hotkeys', {}))
        self.hotkey_manager.start_resume_triggered.connect(self.logic.start_or_resume)
        self.hotkey_manager.pause_triggered.connect(self.logic.pause)
        self.hotkey_manager.reset_cycle_triggered.connect(self.logic.reset_cycle)
        self.hotkey_manager.start()

        self.countdown_timer = QTimer(self)
        self.countdown_timer.setInterval(1000)
        self.countdown_timer.timeout.connect(self.update_countdown_display)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint if self.is_always_on_top else Qt.WindowType.Widget
        )
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.background_widget = QWidget(self)
        self.background_widget.setObjectName("background")

        bg_layout = QVBoxLayout(self.background_widget)
        bg_layout.setContentsMargins(10, 10, 10, 0)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setWordWrap(True)
        
        self.total_time_label = QLabel()
        self.total_time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.total_time_label.setObjectName("total_time_label")
        
        bg_layout.addWidget(self.status_label)
        bg_layout.addWidget(self.total_time_label)
        bg_layout.addStretch()

        grip_layout = QHBoxLayout()
        grip_layout.setContentsMargins(0, 0, 0, 0)
        grip_layout.addStretch()
        self.size_grip = QSizeGrip(self.background_widget)
        grip_layout.addWidget(self.size_grip)
        bg_layout.addLayout(grip_layout)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.background_widget)

        self.load_settings()
        self.update_stylesheet()

        self.logic.state_changed.connect(self.update_status)
        self.logic.time_updated.connect(self.update_total_time)
        self.logic.notification_requested.connect(self.show_notification)
        
        self.logic.reset_cycle()

    def show_notification(self, title, message):
        self.tray.showMessage(title, message, self.tray_icon, 5000)

    # --- NEW: 打开日志文件夹的方法 ---
    def open_log_folder(self):
        log_dir = resource_path(".") # 获取日志文件所在的目录
        try:
            # 跨平台方式打开文件夹
            if sys.platform == 'win32':
                os.startfile(log_dir)
            elif sys.platform == 'darwin': # macOS
                os.system(f'open "{log_dir}"')
            else: # Linux
                os.system(f'xdg-open "{log_dir}"')
        except Exception as e:
            print(f"无法打开文件夹: {e}")
            QMessageBox.warning(self, "操作失败", f"无法自动打开文件夹。\n请手动前往: {log_dir}")

    def confirm_and_reset_all(self):
        """显示一个确认对话框，如果用户确认，则清空所有记录。"""
        reply = QMessageBox.question(
            self,
            '确认操作',  # 弹窗标题
            "您确定要清空所有累计学习时长吗？\n\n此操作不可撤销，但不会删除 study_log.csv 日志文件(如果想恢复可以手动计算累计时常然后填入配置文件中)。", # 提示信息
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, # 按钮选项
            QMessageBox.StandardButton.No  # 默认选中的按钮
        )

        if reply == QMessageBox.StandardButton.Yes:
            print("用户确认清空所有记录。")
            self.logic.reset_all()

    def populate_context_menu(self, menu: QMenu):
        menu.clear()
        menu.setStyleSheet("""
            QMenu { background-color: #3B4252; border: 1px solid #4C566A; }
            QMenu::item { padding: 8px 20px; color: #ECEFF4; }
            QMenu::item:selected { background-color: #5E81AC; }
            QMenu::item:disabled { color: #4C566A; }
            QMenu::separator { height: 1px; background: #4C566A; margin: 4px 0; }
        """)
        
        hotkey_config = self.config.get('hotkeys', {})

        if self.logic.timer.isActive() or self.logic.is_paused:
            remaining_ms = self.logic.time_remaining_on_pause if self.logic.is_paused else self.logic.timer.remainingTime()
            mins, secs = divmod(remaining_ms // 1000, 60)
            status_text = f"⏳ {self.logic.current_state.replace('_', ' ')}: {int(mins)}m {int(secs)}s"
            info_action = QAction(status_text, self); info_action.setDisabled(True)
            menu.addAction(info_action)
            # menu.addSeparator()
        # 新增: 显示距离长休息的剩余时间
        # 仅在计时器未停止时显示此信息
        if self.logic.current_state != 'stopped':
            long_break_threshold = self.config.get("long_break_threshold", 90 * 60)
            current_study_time = self.logic.total_study_time
            
            # 如果还没到长休息时间
            if current_study_time < long_break_threshold:
                remaining_seconds = long_break_threshold - current_study_time
                mins, secs = divmod(remaining_seconds, 60)
                # 在学习状态时，额外加上当前轮次剩余的时间
                if self.logic.current_state == "studying" and self.logic.timer.isActive():
                    timer_remaining_secs = self.logic.timer.remainingTime() // 1000
                    remaining_seconds -= timer_remaining_secs
                    mins, secs = divmod(remaining_seconds, 60)

                long_break_status_text = f"🎯 距长休息约: {int(mins)}分"
            else:
                # 如果已经达到或超过长休息时间
                long_break_status_text = "🎉 已可进入长休息"

            long_break_action = QAction(long_break_status_text, self)
            long_break_action.setDisabled(True) # 设为禁用，仅作为信息展示
            menu.addAction(long_break_action)
        menu.addSeparator()

        is_running = self.logic.timer.isActive()
        is_paused = self.logic.is_paused

        start_hotkey = hotkey_config.get('start_resume', '')
        start_text = "▶️ 开始 / 继续" + (f"  ({start_hotkey})" if start_hotkey else "")
        start_action = QAction(start_text, self)
        start_action.triggered.connect(self.logic.start_or_resume)
        if is_running and not is_paused: start_action.setDisabled(True)
        
        pause_hotkey = hotkey_config.get('pause', '')
        pause_text = "⏸️ 暂 停" + (f"  ({pause_hotkey})" if pause_hotkey else "")
        pause_action = QAction(pause_text, self)
        pause_action.triggered.connect(self.logic.pause)
        if not is_running or is_paused: pause_action.setDisabled(True)

        lock_text = "🔓 解锁 (可交互)" if self.is_locked else "🔒 锁定 (鼠标穿透)"
        lock_action = QAction(lock_text, self); lock_action.triggered.connect(self.toggle_mouse_penetration)
        
        always_on_top_text = f"{'✅' if self.is_always_on_top else '🔲'} 总在最前"
        always_on_top_action = QAction(always_on_top_text, self); always_on_top_action.triggered.connect(self.toggle_always_on_top)

        opacity_menu = QMenu("💧 透明度", self)
        for val in [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4,0.3,0.2,0.1,0.0]:
            op_action = QAction(f"{int(val*100)}%", self); op_action.triggered.connect(lambda _, v=val: self.set_opacity(v))
            opacity_menu.addAction(op_action)
            
        reset_menu = QMenu("🔄 重置", self)
        
        reset_cycle_hotkey = hotkey_config.get('reset_cycle', '')
        reset_cycle_text = "重置当前轮次" + (f"  ({reset_cycle_hotkey})" if reset_cycle_hotkey else "")
        reset_cycle_action = QAction(reset_cycle_text, self)
        reset_cycle_action.triggered.connect(self.logic.reset_cycle)
        
        clear_all_action = QAction("🗑️ 清空所有记录", self); clear_all_action.triggered.connect(self.confirm_and_reset_all)
        reset_menu.addAction(reset_cycle_action)
        reset_menu.addAction(clear_all_action)
        
        # --- NEW: "打开日志" 菜单项 ---
        open_log_action = QAction("📂 打开日志文件夹", self)
        open_log_action.triggered.connect(self.open_log_folder)

        quit_action = QAction("❌ 退 出", self); quit_action.triggered.connect(self.close)

        menu.addAction(start_action)
        menu.addAction(pause_action)
        menu.addSeparator()
        menu.addAction(lock_action)
        menu.addAction(always_on_top_action)
        menu.addMenu(opacity_menu)
        menu.addMenu(reset_menu)
        menu.addAction(open_log_action) # <--- NEW
        menu.addSeparator()
        menu.addAction(quit_action)

    # --- 以下方法基本不变 ---
    def update_stylesheet(self):
        opacity = self.settings.value("ui/opacity", 0.8, type=float)
        border_style = "border: none;" if self.is_locked else "border: 1px solid #88C0D0;"
        self.background_widget.setStyleSheet(f"""
            #background {{ background-color: rgba(46, 52, 64, {opacity}); border-radius: 10px; {border_style} }}
            QLabel {{ background-color: transparent; color: #D8DEE9; font-family: 'Microsoft YaHei', 'Segoe UI', Arial, sans-serif; font-size: 15px; }}
            #total_time_label {{ font-size: 12px; color: #A3BE8C; padding-top: 5px; }}
            QSizeGrip {{ background-color: transparent; width: 15px; height: 15px; }}
        """)

    def update_status(self, status_text, state_name):
        if state_name == "long_breaking":
            self.countdown_timer.start()
            self.update_countdown_display()
        else:
            self.countdown_timer.stop()
            self.status_label.setText(status_text)
        self.update_stylesheet()
        
    def update_countdown_display(self):
        if self.logic.timer.isActive():
            remaining_ms = self.logic.timer.remainingTime()
            mins, secs = divmod(remaining_ms // 1000, 60)
            self.status_label.setText(f"🧘 长休息\n{int(mins):02}:{int(secs):02}")

    def create_tray_icon(self):
        self.tray_icon = QIcon(resource_path('icon.ico'))
        self.tray = QSystemTrayIcon(self.tray_icon, self)
        self.tray.setToolTip("沉浸式学习计时器")
        self.tray_menu = QMenu(self)
        self.tray_menu.aboutToShow.connect(self.update_tray_menu)
        self.tray.setContextMenu(self.tray_menu)
        self.tray.show()
        self.tray.activated.connect(lambda r: self.toggle_mouse_penetration() if r == QSystemTrayIcon.ActivationReason.Trigger else None)

    def update_tray_menu(self):
        self.populate_context_menu(self.tray_menu)

    def contextMenuEvent(self, event):
        if self.is_locked: return
        context_menu = QMenu(self)
        self.populate_context_menu(context_menu)
        context_menu.exec(event.globalPos())

    def toggle_mouse_penetration(self):
        self.is_locked = not self.is_locked
        self.size_grip.setVisible(not self.is_locked)
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, self.is_locked)
        self.show()
        if not self.is_locked: self.activateWindow()
        self.update_stylesheet()

    def toggle_always_on_top(self):
        self.is_always_on_top = not self.is_always_on_top
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.is_always_on_top)
        self.show()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.toggle_mouse_penetration()

    def mousePressEvent(self, event):
        if not self.is_locked and event.button() == Qt.MouseButton.LeftButton:
            if self.size_grip.geometry().contains(event.pos()): return
            self.dragPos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if not self.is_locked and event.buttons() == Qt.MouseButton.LeftButton and self.dragPos:
            self.move(event.globalPosition().toPoint() - self.dragPos)
    
    def mouseReleaseEvent(self, event):
        self.dragPos = None

    def closeEvent(self, event):
        self.logic._clear_current_session() # 确保退出时不记录未完成的会话
        self.save_settings()
        if not self._init_failed:
            self.config['total_study_time'] = self.logic.total_study_time
            save_config(self.config)
            self.logic.stop()
            self.hotkey_manager.stop()
            self.tray.hide()
        event.accept()
        QApplication.quit()
        
    def update_total_time(self, total_seconds):
        self.total_time_label.setText(f"累计学习: {total_seconds // 3600}h {(total_seconds // 60) % 60}m")
        
    def set_opacity(self, value):
        self.settings.setValue("ui/opacity", value)
        self.update_stylesheet()

    def save_settings(self):
        if self._init_failed: return
        self.settings.setValue("ui/geometry", self.saveGeometry())
        self.settings.setValue("ui/opacity", self.settings.value("ui/opacity", 0.8))
        self.settings.setValue("ui/alwaysOnTop", self.is_always_on_top)

    def load_settings(self):
        geometry = self.settings.value("ui/geometry")
        if geometry: self.restoreGeometry(geometry)
        else: self.resize(220, 120)
        self.update_total_time(self.logic.total_study_time)

# ==============================================================================
# 程序主入口
# ==============================================================================
if __name__ == "__main__":
    if keyboard is None:
        error_app = QApplication(sys.argv)
        show_pynput_error()
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not os.path.exists(resource_path('icon.ico')):
        QMessageBox.critical(None, "资源错误", "关键文件 'icon.ico' 未找到！\n程序无法启动。")
        sys.exit(1)

    config = load_or_create_config()
    window = StudyTimerGUI(config)
    
    if window._init_failed:
        sys.exit(1)

    window.show()
    sys.exit(app.exec())
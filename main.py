import os
import sys
import json
import pandas as pd
import asyncio
from PyQt5 import uic
from PyQt5.QtGui import QColor, QPalette, QBrush, QPixmap, QIcon
from PyQt5.QtWidgets import QApplication, QMainWindow, QMessageBox, QTableWidgetItem, QPushButton, \
     QFileDialog
from PyQt5.QtCore import QThread, pyqtSignal, QFileInfo, QByteArray, QTimer, Qt
from ssh_manager import SSHManager
from upgrade_manager import UpgradeManager


class UpgradeWorker(QThread):
    finished = pyqtSignal(int, str, str)  # 行号，状态，消息
    progress = pyqtSignal(int, int)  # 进度信号

    def __init__(self, coro, row):
        super().__init__()
        self.coro = coro
        self.row = row

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.report_progress = lambda p: self.progress.emit(self.row, p)
            result = loop.run_until_complete(self.coro)
            self.finished.emit(self.row, "Success", str(result))
        except Exception as e:
            self.finished.emit(self.row, "Fail", str(e))
        finally:
            loop.close()


class MainWindow(QMainWindow):
    """
    主窗口类，继承自QMainWindow。
    提供UI界面和升级内核的功能。
    """

    CONFIG_FILE = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))),
                               'config.json')  # 保存配置文件路径
    INITIAL_COLUMN_WIDTHS = {
        0: 100,  # Host
        1: 80,  # Username
        2: 80,  # Password
        3: 80,  # State
        4: 215,  # Logs
        5: 80,  # Upgrade
        6: 80  # Delete
    }  # 定义表格初始列宽
    update_gui_signal = pyqtSignal(int, str, str)  # 用于更新 GUI 的信号

    def __init__(self):
        """
        初始化主窗口。
        """
        super().__init__()
        self._last_opened_dir = ''
        self.running_tasks = set()
        self.upgrade_workers = []
        self.total_tasks = 0
        self.upgrade_progresses = {}
        self.upgrade_statuses = {}
        self.update_overall_progress()
        self.is_upgrading_all = False

        self.init_ui()
        self.set_app_icon()
        self.set_background()
        self.setup_connections()

        self.load_config()

    def init_ui(self):
        """
        初始化UI界面。
        """
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        ui_path = os.path.join(base_path, 'ui/main_window.ui')
        uic.loadUi(ui_path, self)

        self.setup_table()
        self.setup_progress_bar()

    def set_app_icon(self):
        """
        设置应用程序图标
        """
        icon_path = os.path.join(self.get_resource_path(), 'icon.png')
        if os.path.exists(icon_path):
            app_icon = QIcon(icon_path)
            self.setWindowIcon(app_icon)
        else:
            print(f"警告: 图标文件 {icon_path} 不存在")

    def set_background(self):
        """
        设置应用程序背景
        """
        background_path = os.path.join(self.get_resource_path(), 'background.png')
        if os.path.exists(background_path):
            background = QPixmap(background_path)
            palette = QPalette()
            palette.setBrush(QPalette.Background, QBrush(background))
            self.setPalette(palette)
        else:
            print(f"警告: 背景图片 {background_path} 不存在")

    def get_resource_path(self):
        """
        获取资源文件路径
        """
        if getattr(sys, 'frozen', False):
            # 如果是打包后的可执行文件
            base_path = sys._MEIPASS
        else:
            # 如果是开发环境
            base_path = os.path.dirname(os.path.abspath(__file__))

        return os.path.join(base_path, 'resources')

    def setup_table(self):
        """
        初始化表格。
        """
        self.upgradeTasksTable.setColumnCount(7)
        self.upgradeTasksTable.setHorizontalHeaderLabels(
            ['Host', 'Username', 'Password', 'State', 'Logs', 'Upgrade', 'Delete'])
        for col, width in self.INITIAL_COLUMN_WIDTHS.items():
            self.upgradeTasksTable.setColumnWidth(col, width)
        self.upgradeTasksTable.verticalHeader().setDefaultSectionSize(40)  # 设置表格行高

    def setup_progress_bar(self):
        """
        初始化进度条。
        """
        self.set_progress_bar_color("rgba(5, 184, 204, 0.5)")  # 默认蓝色，50% 不透明度
        self.overallProgressBar.setFixedHeight(2)  # 设置进度条高度为2像素

    def setup_connections(self):
        self.addUpgradeTaskButton.clicked.connect(self.add_ssh_config)
        self.upgradeAllHostsButton.clicked.connect(self.upgrade_all)
        self.upgradeFileButton.clicked.connect(self.select_upgrade_file)
        self.upgradeScriptButton.clicked.connect(self.select_upgrade_script)
        self.importButton.clicked.connect(self.import_ssh_configs)
        self.exportButton.clicked.connect(self.export_ssh_configs)
        self.clearTasksButton.clicked.connect(self.clear_ssh_configs)
        self.update_gui_signal.connect(self.update_gui)

    def select_upgrade_file(self):
        """
        选择升级文件。
        """
        initial_dir = self.get_last_opened_dir()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Upgrade File", initial_dir, "All Files (*)")
        if file_path:
            self.upgradeFileEntry.setText(file_path)
            self.save_last_opened_dir(file_path)

    def select_upgrade_script(self):
        """
        选择升级脚本。
        """
        initial_dir = self.get_last_opened_dir()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Upgrade Script", initial_dir,
                                                   "Shell Scripts (*.sh);;All Files (*)")
        if file_path:
            self.upgradeScriptEntry.setText(file_path)
            self.save_last_opened_dir(file_path)

    def add_upgrade_task(self, host, username, password):
        """
        添加新的升级任务。
        """
        row_position = self.upgradeTasksTable.rowCount()
        self.upgradeTasksTable.insertRow(row_position)
        self.upgradeTasksTable.setItem(row_position, 0, host)
        self.upgradeTasksTable.setItem(row_position, 1, username)
        self.upgradeTasksTable.setItem(row_position, 2, password)

        upgrade_button = QPushButton('Upgrade')
        upgrade_button.clicked.connect(lambda _, r=row_position: self.upgrade_host(r))
        upgrade_button.setStyleSheet("color: #0067c0;")
        self.upgradeTasksTable.setCellWidget(row_position, 5, upgrade_button)

        delete_button = QPushButton('Delete')
        delete_button.clicked.connect(lambda _, r=row_position: self.remove_upgrade_task(r))
        delete_button.setStyleSheet("color: #d32f2f;")
        self.upgradeTasksTable.setCellWidget(row_position, 6, delete_button)

    def add_ssh_config(self):
        """
        添加新的SSH配置。
        """
        host = self.hostEntry.text()
        username = self.usernameEntry.text()
        password = self.passwordEntry.text()
        if host and username and password:
            self.add_upgrade_task(QTableWidgetItem(host),
                                  QTableWidgetItem(username),
                                  QTableWidgetItem(password))
        self.update_task_count()

    def remove_upgrade_task(self, row):
        """
        删除指定的升级任务。
        """
        self.upgradeTasksTable.removeRow(row)
        # 更新所有升级和删除按钮的lambda函数
        for i in range(self.upgradeTasksTable.rowCount()):
            upgrade_button = self.upgradeTasksTable.cellWidget(i, 5)
            upgrade_button.clicked.disconnect()
            upgrade_button.clicked.connect(lambda _, r=i: self.upgrade_host(r))

            delete_button = self.upgradeTasksTable.cellWidget(i, 6)
            delete_button.clicked.disconnect()
            delete_button.clicked.connect(lambda _, r=i: self.remove_upgrade_task(r))

        # 更新任务数量
        self.update_task_count()

    def update_task_count(self):
        """
        更新任务数量。
        """
        task_count = self.upgradeTasksTable.rowCount()
        self.total_tasks = task_count
        new_progresses = {row: self.upgrade_progresses.get(row, 0) for row in range(task_count)}
        self.upgrade_progresses = new_progresses
        new_statuses = {row: self.upgrade_statuses.get(row, "") for row in range(task_count)}
        self.upgrade_statuses = new_statuses
        self.update_overall_progress()  # 更新任务数量后，更新总体进度

    def clear_ssh_configs(self):
        """
        清空SSH配置。
        """
        reply = QMessageBox.question(self, '确认清除',
                                     '您确定要清除所有任务吗？\n'
                                     '这将停止所有正在运行的升级。',
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.stop_all_tasks()
        else:
            return

        self.upgradeTasksTable.clearContents()
        self.upgradeTasksTable.setRowCount(0)
        self.upgrade_progresses.clear()
        self.upgrade_statuses.clear()
        self.overallProgressBar.setValue(0)
        self.reset_progress_bar_color()

    def stop_all_tasks(self):
        """
        停止所有任务。
        """
        for worker in list(self.running_tasks):
            worker.terminate()
            worker.wait()
            self.running_tasks.remove(worker)
        self.upgrade_workers.clear()
        self.upgradeAllHostsButton.setEnabled(True)
        self.overallProgressBar.setValue(0)
        self.reset_progress_bar_color()

    async def connect_ssh(self, row):
        """
        连接SSH并执行升级操作。
        """
        host = self.upgradeTasksTable.item(row, 0).text()
        username = self.upgradeTasksTable.item(row, 1).text()
        password = self.upgradeTasksTable.item(row, 2).text()
        ssh_manager = SSHManager(host, username, password)
        upgrade_manager = UpgradeManager(ssh_manager)
        try:
            result = await upgrade_manager.execute_upgrade_async()
            if isinstance(result, str):  # 如果是错误消息
                raise Exception(result)
            stdout, stderr = result
            if stderr:
                raise Exception(stderr)
            self.upgradeTasksTable.setItem(row, 3, QTableWidgetItem("Success"))
            self.upgradeTasksTable.setItem(row, 4, QTableWidgetItem(stdout))
        except Exception as e:
            self.upgradeTasksTable.setItem(row, 3, QTableWidgetItem("Fail"))
            self.upgradeTasksTable.setItem(row, 4, QTableWidgetItem(str(e)))

    def upgrade_all(self):
        """
        为所有SSH配置创建并启动异步工作线程。
        """
        if self.upgradeTasksTable.rowCount() == 0:
            QMessageBox.warning(self, "警告", "没有添加任何任务!\n"
                                            "请先添加至少一个升级任务。")
            return

        upgrade_file = self.upgradeFileEntry.text()
        upgrade_script = self.upgradeScriptEntry.text()
        if not upgrade_file or not upgrade_script:
            QMessageBox.warning(self, "警告", "请选择升级文件和脚本。")
            return

        self.is_upgrading_all = True  # 设置标志，表示正在执行"升级全部"操作
        self.upgradeAllHostsButton.setEnabled(False)  # 禁用“连接全部”按钮
        self.overallProgressBar.setValue(0)
        self.reset_progress_bar_color()
        self.total_tasks = self.upgradeTasksTable.rowCount()
        self.upgrade_progresses = {row: 0 for row in range(self.total_tasks)}
        self.upgrade_statuses = {row: "" for row in range(self.total_tasks)}
        for row in range(self.total_tasks):
            self.upgrade_host(row)

        self.set_all_buttons_enabled(False)

    def upgrade_host(self, row):
        """
        为指定的SSH配置创建并启动异步工作线程。
        """
        host = self.upgradeTasksTable.item(row, 0).text()
        username = self.upgradeTasksTable.item(row, 1).text()
        password = self.upgradeTasksTable.item(row, 2).text()
        upgrade_file = self.upgradeFileEntry.text()
        upgrade_script = self.upgradeScriptEntry.text()

        if not upgrade_file or not upgrade_script:
            QMessageBox.warning(self, "警告", "请选择升级文件和脚本。")
            return

        self.upgradeTasksTable.setItem(row, 3, QTableWidgetItem("0%"))
        self.upgradeTasksTable.setItem(row, 4, QTableWidgetItem(""))
        self.upgrade_progresses[row] = 0
        self.upgrade_statuses[row] = "0%"
        self.update_gui_signal.emit(row, "0%", "")  # 显式触发GUI更新

        ssh_manager = SSHManager(host, username, password)
        upgrade_manager = UpgradeManager(ssh_manager)

        worker = UpgradeWorker(upgrade_manager.execute_upgrade_async(upgrade_file, upgrade_script), row)
        worker.finished.connect(self.on_worker_finished)
        worker.progress.connect(self.on_worker_progress)
        self.upgrade_workers.append(worker)
        self.running_tasks.add(worker)
        worker.start()

        self.upgrade_progresses[row] = 0  # 初始化该任务的进度为0
        self.reset_progress_bar_color()

        # 禁用当前行的按钮
        upgrade_button = self.upgradeTasksTable.cellWidget(row, 5)
        upgrade_button.setEnabled(False)
        upgrade_button.setStyleSheet("color: #a0a0a0;")
        delete_button = self.upgradeTasksTable.cellWidget(row, 6)
        delete_button.setEnabled(False)
        delete_button.setStyleSheet("color: #a0a0a0;")
        # 取消选择表格中的单元格
        self.upgradeTasksTable.setCurrentItem(None)
        # 禁用“更新全部”按钮
        self.upgradeAllHostsButton.setEnabled(False)

    def check_upgrade_results(self):
        """
        检查所有升级任务的结果，显示统计信息，如果有失败的任务且正在执行"升级全部"操作，弹出对话框询问是否重新升级。
        """
        if not self.is_upgrading_all:
            return  # 如果不是"升级全部"操作，直接返回

        total_tasks = len(self.upgrade_statuses)
        successful_tasks = sum(1 for status in self.upgrade_statuses.values() if status == "Success")
        failed_tasks = sum(1 for status in self.upgrade_statuses.values() if status == "Fail")

        message = f"升级任务统计:\n" \
                  f"总任务数: {total_tasks}\n" \
                  f"成功数量: {successful_tasks}\n" \
                  f"失败数量: {failed_tasks}\n\n"

        if failed_tasks > 0:
            message += "是否要重新升级失败的任务？"
            reply = QMessageBox.question(self, '升级结果', message,
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.retry_failed_upgrades()
        else:
            QMessageBox.information(self, '升级结果', message)

    def retry_failed_upgrades(self):
        """
        重新升级失败的任务。
        """
        failed_tasks = [row for row, status in self.upgrade_statuses.items() if status == "Fail"]
        for row in failed_tasks:
            self.upgrade_host(row)

    def on_worker_progress(self, row, progress):
        """
        处理异步工作线程的进度更新。
        """
        if self.upgrade_statuses.get(row) != "Fail":
            self.upgrade_progresses[row] = progress
            self.update_gui_signal.emit(row, f"{progress}%", "")
        if not self.upgradeAllHostsButton.isEnabled():
            self.update_overall_progress()
        # print(f"任务 {row} 进度: {progress}%")  # 调试输出

    def on_worker_finished(self, row, status, message):
        """
        处理异步工作线程的完成事件。
        """
        if status == "Fail":
            self.upgrade_progresses[row] = 0
        else:
            self.upgrade_progresses[row] = 100
        self.upgrade_statuses[row] = status
        self.update_gui_signal.emit(row, status, message)
        if not self.upgradeAllHostsButton.isEnabled():
            self.update_overall_progress()

        # print(f"任务 {row} 完成。状态: {status}")  # 调试输出

        for worker in list(self.running_tasks):
            if worker.row == row:
                self.running_tasks.remove(worker)
                break

        # 恢复当前行的按钮状态
        upgrade_button = self.upgradeTasksTable.cellWidget(row, 5)
        delete_button = self.upgradeTasksTable.cellWidget(row, 6)
        if upgrade_button:
            upgrade_button.setEnabled(True)
            upgrade_button.setStyleSheet("color: #0067c0;")
        if delete_button:
            delete_button.setEnabled(True)
            delete_button.setStyleSheet("color: #d32f2f;")

        # 检查是否没有正在执行的任务
        if len(self.running_tasks) == 0:
            QTimer.singleShot(0, lambda: self.upgradeAllHostsButton.setEnabled(True))
            self.set_all_buttons_enabled(True)
            self.check_and_update_progress_bar_color()
            self.check_upgrade_results()
            self.is_upgrading_all = False

    def update_gui(self, row, status, message):
        """
        更新GUI中的表格项。
        """
        status_item = QTableWidgetItem(status)
        message_item = QTableWidgetItem(message)

        if status == "Success":
            status_item.setForeground(QColor("green"))
            message_item.setForeground(QColor("green"))
        elif status == "Fail":
            status_item.setForeground(QColor("red"))
            message_item.setForeground(QColor("red"))
        elif status.endswith("%"):
            status_item.setForeground(QColor("#05B8CC"))
            message_item.setForeground(QColor("#05B8CC"))

        self.upgradeTasksTable.setItem(row, 3, status_item)
        self.upgradeTasksTable.setItem(row, 4, message_item)

    def set_all_buttons_enabled(self, enabled):
        """
        设置所有按钮的启用状态。
        """
        for row in range(self.upgradeTasksTable.rowCount()):
            upgrade_button = self.upgradeTasksTable.cellWidget(row, 5)
            delete_button = self.upgradeTasksTable.cellWidget(row, 6)
            if upgrade_button:
                upgrade_button.setEnabled(enabled)
                upgrade_button.setStyleSheet("color: #0067c0;" if enabled else "color: #a0a0a0;")
            if delete_button:
                delete_button.setEnabled(enabled)
                delete_button.setStyleSheet("color: #d32f2f;" if enabled else "color: #a0a0a0;")

    def update_overall_progress(self):
        """
        更新总体进度。
        """
        if self.total_tasks > 0:
            overall_progress = int(sum(self.upgrade_progresses.values()) / self.total_tasks)
        else:
            overall_progress = 0
        QTimer.singleShot(0, lambda: self.overallProgressBar.setValue(overall_progress))
        # print(f"总体进度: {overall_progress}%")  # 调试输出

    def check_and_update_progress_bar_color(self):
        """
        检查并更新进度条颜色。
        """
        if any(status == "Fail" for status in self.upgrade_statuses.values()):
            self.set_progress_bar_color("rgba(255, 0, 0, 0.5)")  # 红色，50% 不透明度
        elif all(status == "Success" for status in self.upgrade_statuses.values() if status):
            self.set_progress_bar_color("rgba(76, 175, 80, 0.5)")  # 绿色，50%
        else:
            self.set_progress_bar_color("rgba(5, 184, 204, 0.5)")  # 默认蓝色，50% 不透明度

    # 新增方法: 设置进度条颜色
    def set_progress_bar_color(self, color):
        """
        设置进度条颜色。
        """
        self.overallProgressBar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: rgba(204, 204, 204, 0.5);
                height: 100px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)

    def reset_progress_bar_color(self):
        """
        重置进度条颜色。
        """
        self.set_progress_bar_color("rgba(5, 184, 204, 0.5)")  # 默认蓝色，50% 不透明度

    def import_ssh_configs(self):
        """
        导入SSH配置文件。
        """
        initial_dir = self.get_last_opened_dir()
        file_path, _ = QFileDialog.getOpenFileName(self, "Load SSH Configs", initial_dir,
                                                   "CSV Files (*.csv);;All Files (*)")
        if file_path:
            try:
                df = pd.read_csv(file_path)

                # 检查必要的列是否存在
                if not all(column in df.columns for column in ['Host', 'Username', 'Password']):
                    raise ValueError("CSV文件缺少必要的列：'Host', 'Username', 'Password'")

                self.upgradeTasksTable.setRowCount(0)  # 清空表格

                for index, row in df.iterrows():
                    self.add_upgrade_task(QTableWidgetItem(row['Host']),
                                          QTableWidgetItem(row['Username']),
                                          QTableWidgetItem(row['Password']))
                self.update_task_count()
                self.save_last_opened_dir(file_path)
            except pd.errors.EmptyDataError:
                self.show_import_ssh_configs_error_message("CSV文件为空或格式不正确。请检查文件内容。")
            except pd.errors.ParserError:
                self.show_import_ssh_configs_error_message("CSV文件解析错误。请检查文件格式是否正确。")
            except ValueError as ve:
                self.show_import_ssh_configs_error_message(str(ve))
            except Exception as e:
                self.show_import_ssh_configs_error_message(f"发生未知错误: {e}")

    def show_import_ssh_configs_error_message(self, message):
        """
        显示导入SSH配置文件错误消息框。
        """
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("错误")
        msg_box.setText(message)
        msg_box.setInformativeText("请确保文件格式正确并包含以下列：'Host', 'Username', 'Password'。\n"
                                   "例如:\n"
                                   "Host,Username,Password\n"
                                   "192.168.1.1,user,password")
        msg_box.setStandardButtons(QMessageBox.Ok)
        msg_box.exec_()

    def export_ssh_configs(self):
        """
        导出SSH配置文件。
        """
        initial_dir = self.get_last_opened_dir()
        file_path, _ = QFileDialog.getSaveFileName(self, "Save SSH Configs", initial_dir,
                                                   "CSV Files (*.csv);;All Files (*)")
        if file_path:
            data = []
            for row in range(self.upgradeTasksTable.rowCount()):
                data.append({
                    'Host': self.upgradeTasksTable.item(row, 0).text(),
                    'Username': self.upgradeTasksTable.item(row, 1).text(),
                    'Password': self.upgradeTasksTable.item(row, 2).text()
                })
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            self.save_last_opened_dir(file_path)

    def save_config(self):
        """
        保存配置到 config.json 文件。
        """
        config = {
            'geometry': self.saveGeometry().toHex().data().decode(),
            'state': self.saveState().toHex().data().decode(),
            'upgrade_file': self.upgradeFileEntry.text(),
            'upgrade_script': self.upgradeScriptEntry.text(),
            'last_opened_dir': self.get_last_opened_dir() + '/',
            'ssh_configs': [
                {
                    'Host': self.upgradeTasksTable.item(row, 0).text(),
                    'Username': self.upgradeTasksTable.item(row, 1).text(),
                    'Password': self.upgradeTasksTable.item(row, 2).text()
                }
                for row in range(self.upgradeTasksTable.rowCount())
            ],
            'entries': {
                'host': self.hostEntry.text(),
                'username': self.usernameEntry.text(),
                'password': self.passwordEntry.text()
            },
            'table_column_widths': {
                str(i): self.upgradeTasksTable.columnWidth(i)
                for i in range(self.upgradeTasksTable.columnCount())
            }
        }
        with open(self.CONFIG_FILE, 'w') as f:
            json.dump(config, f)

    def load_config(self):
        """
        从 config.json 文件加载配置。
        """
        try:
            with open(self.CONFIG_FILE, 'r') as f:
                config = json.load(f)

                geometry = config.get('geometry')
                state = config.get('state')
                entries = config.get('entries', {})
                host = entries.get('host', '')
                username = entries.get('username', '')
                password = entries.get('password', '')
                upgrade_file = config.get('upgrade_file', '')
                upgrade_script = config.get('upgrade_script', '')
                last_opened_dir = config.get('last_opened_dir', '')
                column_widths = config.get('table_column_widths', {})
                ssh_configs = config.get('ssh_configs', [])

                if geometry:
                    self.restoreGeometry(QByteArray.fromHex(geometry.encode()))
                if state:
                    self.restoreState(QByteArray.fromHex(state.encode()))
                self.upgradeFileEntry.setText(upgrade_file)
                self.upgradeScriptEntry.setText(upgrade_script)
                self.set_last_opened_dir(last_opened_dir)

                self.hostEntry.setText(host)
                self.usernameEntry.setText(username)
                self.passwordEntry.setText(password)

                for col, width in column_widths.items():
                    self.upgradeTasksTable.setColumnWidth(int(col), width)

                for ssh_config in ssh_configs:
                    self.add_upgrade_task(QTableWidgetItem(ssh_config.get('Host', '')),
                                          QTableWidgetItem(ssh_config.get('Username', '')),
                                          QTableWidgetItem(ssh_config.get('Password', '')))
                self.update_task_count()

        except FileNotFoundError:
            # 如果配置文件不存在，不执行任何操作
            pass
        except Exception as e:
            # 捕获并记录其他可能的异常
            print(f"Error loading configuration: {e}")

    def get_last_opened_dir(self):
        """
        获取上次打开的文件夹路径。
        """
        return getattr(self, '_last_opened_dir', '')

    def set_last_opened_dir(self, path):
        """
        设置上次打开的文件夹路径。
        """
        self._last_opened_dir = QFileInfo(path).absolutePath() if path else ''

    def save_last_opened_dir(self, path):
        """
        保存上次打开的文件夹路径。
        """
        self.set_last_opened_dir(path)
        self.save_config()

    def closeEvent(self, event):
        """
        处理窗口关闭事件，确保在关闭前保存配置。
        """
        self.save_config()
        event.accept()


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())

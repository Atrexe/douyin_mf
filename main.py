#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import json
import requests
import re
import tempfile
import shutil
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QRadioButton, QButtonGroup,
    QTextEdit, QProgressBar, QMessageBox, QFileDialog, QTabWidget,
    QGroupBox, QFormLayout, QCheckBox
)
from PyQt5.QtGui import QIcon, QPixmap, QFont, QDesktopServices
from PyQt5.QtCore import Qt, QUrl, QThread, pyqtSignal, QSize

class VideoParserThread(QThread):
    """
    视频解析线程，用于后台处理解析请求
    """
    result_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)
    
    def __init__(self, url, api_url, direct_play=False):
        """
        初始化线程
        
        @param {string} url - 需要解析的视频URL
        @param {string} api_url - 解析接口地址
        @param {boolean} direct_play - 是否直接播放
        """
        super().__init__()
        self.url = url
        self.api_url = api_url
        self.direct_play = direct_play
        
    def run(self):
        """执行解析任务"""
        try:
            params = {
                'url': self.url
            }
            
            if self.direct_play:
                params['type'] = 'down'
                
            response = requests.get(self.api_url, params=params, timeout=15)
            if response.status_code == 200:
                result = response.json()
                self.result_signal.emit(result)
            else:
                self.error_signal.emit(f"请求失败，状态码：{response.status_code}")
        except Exception as e:
            self.error_signal.emit(f"解析出错: {str(e)}")

class VideoDownloadThread(QThread):
    """
    视频下载线程，用于后台下载视频并保存为指定文件名
    """
    progress_signal = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, url, save_path):
        """
        初始化下载线程
        
        @param {string} url - 视频下载链接
        @param {string} save_path - 保存路径
        """
        super().__init__()
        self.url = url
        self.save_path = save_path
        self.is_cancelled = False
        self.temp_file = None
        
    def run(self):
        """执行下载任务"""
        try:
            # 设置请求头，模拟完整的浏览器环境
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Referer": self.url,
                "Sec-Fetch-Dest": "video",
                "Sec-Fetch-Mode": "no-cors",
                "Sec-Fetch-Site": "cross-site",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "Origin": "https://api.kxzjoker.cn"
            }
            
            # 创建临时文件
            self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            self.temp_file.close()
            
            # 尝试使用会话保持连接状态
            with requests.Session() as session:
                # 先访问一次来源页面
                try:
                    session.get("https://api.kxzjoker.cn/", headers=headers, timeout=5)
                except:
                    pass  # 忽略可能的错误
                
                # 发送流式请求
                response = session.get(self.url, headers=headers, stream=True, timeout=30)
                response.raise_for_status()
                
                # 获取总大小
                total_size = int(response.headers.get('content-length', 0))
                if total_size == 0:
                    self.finished_signal.emit(False, "无法获取文件大小，下载可能不完整")
                    self._clean_temp_file()
                    return
                    
                # 写入临时文件
                downloaded_size = 0
                with open(self.temp_file.name, 'wb') as file:
                    for chunk in response.iter_content(chunk_size=8192):
                        if self.is_cancelled:
                            # 取消下载
                            file.close()
                            self._clean_temp_file()
                            self.finished_signal.emit(False, "下载已取消")
                            return
                            
                        if chunk:
                            file.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # 更新进度
                            progress = int((downloaded_size / total_size) * 100)
                            self.progress_signal.emit(progress)
                
                # 下载完成后，将临时文件复制到目标位置
                try:
                    # 确保目标目录存在
                    target_dir = os.path.dirname(self.save_path)
                    if target_dir and not os.path.exists(target_dir):
                        os.makedirs(target_dir, exist_ok=True)
                        
                    # 移动文件
                    shutil.move(self.temp_file.name, self.save_path)
                    self.temp_file = None
                    
                    # 下载完成
                    self.finished_signal.emit(True, "下载完成")
                except PermissionError:
                    self.finished_signal.emit(False, "保存文件失败: 权限被拒绝，请检查文件路径或权限设置")
                    self._clean_temp_file()
                except FileExistsError:
                    self.finished_signal.emit(False, "保存文件失败: 文件已存在且无法覆盖")
                    self._clean_temp_file()
                except FileNotFoundError:
                    self.finished_signal.emit(False, "保存文件失败: 无法创建或访问目标文件路径")
                    self._clean_temp_file()
                except OSError as e:
                    self.finished_signal.emit(False, f"保存文件失败: 系统错误 - {str(e)}")
                    self._clean_temp_file()
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                self.finished_signal.emit(False, f"下载失败: 服务器拒绝访问(403)，可能需要通过浏览器下载")
            else:
                self.finished_signal.emit(False, f"下载失败: HTTP错误 {e.response.status_code}")
            self._clean_temp_file()
        except requests.exceptions.ConnectionError:
            self.finished_signal.emit(False, "下载失败: 连接错误，请检查网络连接")
            self._clean_temp_file()
        except requests.exceptions.Timeout:
            self.finished_signal.emit(False, "下载失败: 连接超时，请稍后重试")
            self._clean_temp_file()
        except requests.exceptions.RequestException as e:
            self.finished_signal.emit(False, f"下载失败: 请求异常 - {str(e)}")
            self._clean_temp_file()
        except Exception as e:
            self.finished_signal.emit(False, f"下载失败: {str(e)}")
            self._clean_temp_file()
            
    def _clean_temp_file(self):
        """清理临时文件"""
        if self.temp_file and os.path.exists(self.temp_file.name):
            try:
                os.unlink(self.temp_file.name)
            except:
                pass  # 忽略清理临时文件时的错误
            
    def cancel(self):
        """取消下载"""
        self.is_cancelled = True

class VideoParserApp(QMainWindow):
    """视频解析应用主窗口"""
    
    def __init__(self):
        """初始化应用界面"""
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        """初始化用户界面"""
        # 设置窗口基本属性
        self.setWindowTitle("全能视频解析工具")
        self.setMinimumSize(800, 600)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 标题标签
        title_label = QLabel("全能视频解析工具")
        title_label.setAlignment(Qt.AlignCenter)
        title_font = QFont("微软雅黑", 18, QFont.Bold)
        title_label.setFont(title_font)
        title_label.setStyleSheet("color: #2C3E50; margin: 10px;")
        main_layout.addWidget(title_label)
        
        # 输入区域
        input_group = QGroupBox("链接输入")
        input_layout = QVBoxLayout()
        
        # 视频链接输入
        url_layout = QHBoxLayout()
        url_label = QLabel("视频链接:")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("请输入需要解析的视频链接")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        input_layout.addLayout(url_layout)
        
        # API选择区域
        api_select_layout = QHBoxLayout()
        api_label = QLabel("选择API:")
        self.api_group = QButtonGroup()
        self.api1_radio = QRadioButton("线路1 (支持视频和图集)")
        self.api2_radio = QRadioButton("线路2 (仅支持视频)")
        self.api1_radio.setChecked(True)
        self.api_group.addButton(self.api1_radio, 1)
        self.api_group.addButton(self.api2_radio, 2)
        
        api_select_layout.addWidget(api_label)
        api_select_layout.addWidget(self.api1_radio)
        api_select_layout.addWidget(self.api2_radio)
        api_select_layout.addStretch(1)
        
        # 直接播放选项
        self.direct_play_checkbox = QCheckBox("直接播放无水印视频")
        api_select_layout.addWidget(self.direct_play_checkbox)
        
        input_layout.addLayout(api_select_layout)
        
        # 操作按钮
        button_layout = QHBoxLayout()
        self.parse_button = QPushButton("解析视频")
        self.parse_button.setFixedHeight(40)
        self.parse_button.setStyleSheet("""
            QPushButton {
                background-color: #3498DB;
                color: white;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
            QPushButton:pressed {
                background-color: #1A5276;
            }
        """)
        
        self.clear_button = QPushButton("清空内容")
        self.clear_button.setFixedHeight(40)
        self.clear_button.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C;
                color: white;
                border-radius: 5px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
            QPushButton:pressed {
                background-color: #922B21;
            }
        """)
        
        button_layout.addWidget(self.parse_button)
        button_layout.addWidget(self.clear_button)
        input_layout.addLayout(button_layout)
        
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)
        
        # 结果展示区域
        result_group = QGroupBox("解析结果")
        result_layout = QVBoxLayout()
        
        # 添加进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # 设置为不确定模式
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setMaximumHeight(10)
        self.progress_bar.hide()
        result_layout.addWidget(self.progress_bar)
        
        # 添加下载进度条
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 100)
        self.download_progress.setValue(0)
        self.download_progress.setFormat("%p%")
        self.download_progress.setAlignment(Qt.AlignCenter)
        self.download_progress.hide()
        result_layout.addWidget(self.download_progress)
        
        # 结果标签
        self.result_tab = QTabWidget()
        
        # 基本信息标签页
        info_widget = QWidget()
        info_layout = QFormLayout()
        
        self.title_label = QLabel("未解析")
        self.video_url_label = QLabel("未解析")
        self.video_url_label.setWordWrap(True)
        self.video_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        self.download_url_label = QLabel("未解析")
        self.download_url_label.setWordWrap(True)
        self.download_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        self.image_url_label = QLabel("未解析")
        self.image_url_label.setWordWrap(True)
        self.image_url_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        info_layout.addRow("视频标题:", self.title_label)
        info_layout.addRow("视频链接:", self.video_url_label)
        info_layout.addRow("下载链接:", self.download_url_label)
        info_layout.addRow("封面图片:", self.image_url_label)
        
        info_widget.setLayout(info_layout)
        
        # 操作按钮区域
        action_layout = QHBoxLayout()
        
        self.copy_video_btn = QPushButton("复制视频链接")
        self.copy_video_btn.setStyleSheet("background-color: #2ECC71; color: white;")
        
        self.open_video_btn = QPushButton("打开视频")
        self.open_video_btn.setStyleSheet("background-color: #3498DB; color: white;")
        
        self.save_video_btn = QPushButton("保存视频")
        self.save_video_btn.setStyleSheet("background-color: #9B59B6; color: white;")
        
        self.open_in_browser_btn = QPushButton("浏览器下载")
        self.open_in_browser_btn.setStyleSheet("background-color: #F39C12; color: white;")
        
        self.cancel_download_btn = QPushButton("取消下载")
        self.cancel_download_btn.setStyleSheet("background-color: #E74C3C; color: white;")
        self.cancel_download_btn.hide()
        
        action_layout.addWidget(self.copy_video_btn)
        action_layout.addWidget(self.open_video_btn)
        action_layout.addWidget(self.save_video_btn)
        action_layout.addWidget(self.open_in_browser_btn)
        action_layout.addWidget(self.cancel_download_btn)
        
        result_layout.addLayout(action_layout)
        
        # JSON标签页
        self.json_text = QTextEdit()
        self.json_text.setReadOnly(True)
        
        # 添加标签页
        self.result_tab.addTab(info_widget, "基本信息")
        self.result_tab.addTab(self.json_text, "JSON数据")
        
        result_layout.addWidget(self.result_tab)
        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        
        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)  # 禁用右下角大小控制点
        
        # 添加永久标签到状态栏右侧
        free_label = QLabel("本工具永久免费提供")
        free_label_font = QFont("微软雅黑", 9)
        free_label_font.setBold(True)
        free_label.setFont(free_label_font)
        free_label.setStyleSheet("color: #E74C3C;")
        self.status_bar.addPermanentWidget(free_label)  # addPermanentWidget会将控件添加到状态栏右侧
        
        # 设置默认状态消息
        self.status_bar.showMessage("准备就绪")
        
        # 连接信号
        self.parse_button.clicked.connect(self.parse_video)
        self.clear_button.clicked.connect(self.clear_content)
        self.copy_video_btn.clicked.connect(lambda: self.copy_to_clipboard(self.video_url_label.text()))
        self.open_video_btn.clicked.connect(lambda: self.open_url(self.video_url_label.text()))
        self.save_video_btn.clicked.connect(self.save_video)
        self.open_in_browser_btn.clicked.connect(lambda: self.open_url(self.download_url_label.text()))
        self.cancel_download_btn.clicked.connect(self.cancel_download)
        
        # 初始化UI状态
        self.reset_ui_state()
        
    def reset_ui_state(self):
        """重置UI状态，禁用未解析前的按钮"""
        self.video_url = ""
        self.download_url = ""
        self.copy_video_btn.setEnabled(False)
        self.open_video_btn.setEnabled(False)
        self.save_video_btn.setEnabled(False)
        self.open_in_browser_btn.setEnabled(False)
        self.download_thread = None
    
    def parse_video(self):
        """解析视频链接"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "警告", "请输入视频链接")
            return
            
        # 显示进度条
        self.progress_bar.show()
        self.parse_button.setEnabled(False)
        self.status_bar.showMessage("正在解析，请稍候...")
        
        # 确定API URL
        api_base = "https://api.kxzjoker.cn/api/"
        if self.api1_radio.isChecked():
            api_url = api_base + "jiexi_video"
        else:
            api_url = api_base + "jiexi_video_2"
        
        # 创建并启动解析线程
        self.parser_thread = VideoParserThread(
            url, 
            api_url,
            self.direct_play_checkbox.isChecked()
        )
        self.parser_thread.result_signal.connect(self.handle_result)
        self.parser_thread.error_signal.connect(self.handle_error)
        self.parser_thread.finished.connect(self.on_parsing_finished)
        self.parser_thread.start()
    
    def handle_result(self, result):
        """处理解析结果"""
        if result.get('success'):
            data = result.get('data', {})
            
            # 更新UI信息
            self.title_label.setText(data.get('video_title', '未获取到标题'))
            self.video_url_label.setText(data.get('video_url', '未获取到视频链接'))
            self.download_url_label.setText(data.get('download_url', '未获取到下载链接'))
            self.image_url_label.setText(data.get('image_url', '未获取到封面图片'))
            
            # 存储URL以供后续使用
            self.video_url = data.get('video_url', '')
            self.download_url = data.get('download_url', '')
            
            # 启用按钮
            self.copy_video_btn.setEnabled(bool(self.video_url))
            self.open_video_btn.setEnabled(bool(self.video_url))
            self.save_video_btn.setEnabled(bool(self.download_url))
            self.open_in_browser_btn.setEnabled(bool(self.download_url))
            
            # 修改tips字段
            if 'tips' in result:
                result['tips'] = "全能视频解析工具免费提供"
            
            # 显示完整JSON
            try:
                formatted_json = json.dumps(result, ensure_ascii=False, indent=4)
                self.json_text.setText(formatted_json)
            except Exception as e:
                self.json_text.setText(f"JSON格式化错误: {str(e)}")
                
            self.status_bar.showMessage(f"解析成功，时间: {result.get('time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
        else:
            # 处理失败情况
            error_msg = result.get('msg', '未知错误')
            self.handle_error(error_msg)
    
    def handle_error(self, error_msg):
        """处理错误信息"""
        QMessageBox.critical(self, "解析失败", f"解析视频出错: {error_msg}")
        self.status_bar.showMessage(f"解析失败: {error_msg}")
        self.json_text.setText(f"解析失败: {error_msg}")
    
    def on_parsing_finished(self):
        """解析完成后的处理"""
        self.progress_bar.hide()
        self.parse_button.setEnabled(True)
    
    def copy_to_clipboard(self, text):
        """复制文本到剪贴板"""
        if text and text != "未解析":
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.status_bar.showMessage("已复制到剪贴板", 3000)
    
    def open_url(self, url):
        """打开URL链接"""
        if url and url != "未解析":
            QDesktopServices.openUrl(QUrl(url))
    
    def save_video(self):
        """保存视频到本地，使用视频标题作为文件名"""
        if not self.download_url or self.download_url == "未解析":
            QMessageBox.warning(self, "警告", "没有可用的下载链接")
            return
            
        try:
            # 获取视频标题作为默认文件名
            default_name = self.title_label.text()
            
            # 更严格地清理文件名，移除所有不安全的字符
            # Windows文件名不允许包含以下字符: \ / : * ? " < > | 以及ASCII控制字符
            default_name = re.sub(r'[^\w\u4e00-\u9fa5]', "_", default_name)  # 只保留字母、数字、下划线和中文字符
            
            # 确保文件名不以点或空格开头（这在某些系统上可能导致问题）
            default_name = default_name.strip("_. ")
            
            # 移除连续的下划线
            default_name = re.sub(r'_+', "_", default_name)
            
            # 如果清理后文件名为空，使用默认名称
            if not default_name or default_name == "未解析":
                default_name = "video"
                
            # 限制文件名长度
            if len(default_name) > 100:
                default_name = default_name[:100]
                
            # 选择保存位置
            try:
                file_path, _ = QFileDialog.getSaveFileName(
                    self, 
                    "保存视频", 
                    f"{default_name}.mp4", 
                    "视频文件 (*.mp4);;所有文件 (*.*)"
                )
            except Exception as e:
                QMessageBox.warning(self, "错误", f"创建文件对话框时出错: {str(e)}")
                return
            
            if not file_path:
                return  # 用户取消了保存对话框
                
            try:
                # 检查文件路径是否有效
                directory = os.path.dirname(file_path)
                if directory and not os.path.exists(directory):
                    os.makedirs(directory, exist_ok=True)
                
                # 检查文件名是否合法（再次检查，以防用户在对话框中输入了非法名称）
                if os.path.basename(file_path) == "":
                    QMessageBox.warning(self, "错误", "文件名无效")
                    return
                    
                # 尝试打开文件以检查写入权限
                try:
                    with open(file_path, 'a'):
                        pass
                    os.remove(file_path)  # 删除测试创建的空文件
                except (PermissionError, OSError):
                    QMessageBox.warning(self, "错误", "没有写入权限或文件被占用，请选择其他位置")
                    return
                
                # 显示下载进度条
                self.download_progress.setValue(0)
                self.download_progress.show()
                self.cancel_download_btn.show()
                self.save_video_btn.setEnabled(False)
                
                # 创建下载线程
                self.download_thread = VideoDownloadThread(self.download_url, file_path)
                self.download_thread.progress_signal.connect(self.update_download_progress)
                self.download_thread.finished_signal.connect(self.on_download_finished)
                self.download_thread.start()
                
                self.status_bar.showMessage(f"开始下载视频: {os.path.basename(file_path)}")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"启动下载时出错: {str(e)}")
                self.save_video_btn.setEnabled(True)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"准备下载时出错: {str(e)}")
            self.save_video_btn.setEnabled(True)
    
    def update_download_progress(self, progress):
        """更新下载进度"""
        self.download_progress.setValue(progress)
    
    def on_download_finished(self, success, message):
        """下载完成后的处理"""
        self.download_progress.hide()
        self.cancel_download_btn.hide()
        self.save_video_btn.setEnabled(True)
        
        if success:
            QMessageBox.information(self, "下载成功", message)
        else:
            if "403" in message:
                # 显示特殊提示，建议使用浏览器下载
                QMessageBox.warning(
                    self, 
                    "下载失败", 
                    f"{message}\n\n服务器禁止直接下载，请点击\"浏览器下载\"按钮，通过浏览器下载视频。"
                )
            else:
                QMessageBox.warning(self, "下载失败", message)
            
        self.status_bar.showMessage(message)
        self.download_thread = None
    
    def cancel_download(self):
        """取消下载"""
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.status_bar.showMessage("正在取消下载...")
    
    def clear_content(self):
        """清空输入和结果内容"""
        self.url_input.clear()
        self.title_label.setText("未解析")
        self.video_url_label.setText("未解析")
        self.download_url_label.setText("未解析")
        self.image_url_label.setText("未解析")
        self.json_text.clear()
        self.reset_ui_state()
        self.status_bar.showMessage("已清空内容")

def main():
    """程序入口点"""
    app = QApplication(sys.argv)
    # 设置应用样式
    app.setStyle("Fusion")
    # 创建并显示主窗口
    main_window = VideoParserApp()
    main_window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
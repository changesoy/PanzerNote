# -*- coding: utf-8 -*-
"""
后台文件保存任务
将文件写入操作放到 QThreadPool 中执行，避免大文件保存时 UI 冻结
"""

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal


class SaveTaskSignals(QObject):
    finished = pyqtSignal(bool, str, object)


class SaveTask(QRunnable):
    """后台文件保存任务

    在 QThreadPool 中执行 safe_write，完成后通过信号通知主线程。
    主线程仍需 toPlainText() 获取内容（同步），但磁盘 IO 在后台执行。

    生命周期由 SaveTaskManager 持有：setAutoDelete(False)，
    Manager 在任务完成回调中释放引用。
    """

    def __init__(self, file_guard, filepath, content, encoding):
        super().__init__()
        self.file_guard = file_guard
        self.filepath = filepath
        self.content = content
        self.encoding = encoding
        self.signals = SaveTaskSignals()
        self.setAutoDelete(False)

    def run(self):
        try:
            self.file_guard.safe_write(
                self.filepath, self.content,
                encoding=self.encoding
            )
            self.signals.finished.emit(True, self.filepath, None)
        except Exception as e:
            self.signals.finished.emit(False, self.filepath, e)

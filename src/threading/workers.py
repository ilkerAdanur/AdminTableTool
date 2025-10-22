# src/threading/workers.py
import traceback
from PyQt6.QtCore import QRunnable, QObject, pyqtSignal

class WorkerSignals(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

class Worker(QRunnable):
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:
            print(f"Worker hatası: {e}")
            traceback.print_exc()
            self.signals.error.emit(str(e))
        else:
            self.signals.finished.emit(result)

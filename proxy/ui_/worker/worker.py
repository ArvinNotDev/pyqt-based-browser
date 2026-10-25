from PySide6.QtCore import Signal, QObject, QRunnable, Slot
from .utils import QRWorkerSignals

    
class Worker(QRunnable):

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = QRWorkerSignals()

    
    @Slot()
    def run(self):
        cancel_event = self.kwargs.get("cancel_event")

        def cancelled():
            is_set = getattr(cancel_event, "is_set", None)
            return bool(callable(is_set) and is_set())

        if cancelled():
            return
        try:
            self.signals.started.emit()
            if cancelled():
                return
            result = self.fn(*self.args, **self.kwargs)
            if cancelled():
                return
            result = "" if result is None else result
            self.signals.finished.emit(str(result))
        except Exception as exc:
            if not cancelled():
                self.signals.error.emit(str(exc))
            
            
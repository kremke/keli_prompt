"""QThread worker infrastructure for Keli Prompt."""

from typing import Callable, Any
from PySide6.QtCore import QObject, Signal


class Worker(QObject):
    """
    Generic worker that runs a callable in a QThread.

    Usage::

        worker = Worker(my_fn, arg1, arg2, kwarg=val)
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        worker.progress.connect(some_slot)
        worker.error.connect(error_slot)
        thread.start()

    The callable receives the worker itself as its first positional argument so
    it can emit ``worker.progress`` messages and check ``worker.is_cancelled``.
    """

    progress: Signal = Signal(str)   # human-readable status message
    finished: Signal = Signal()
    error: Signal = Signal(str)

    def __init__(self, fn: Callable, *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._cancelled: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._fn(self, *self._args, **self._kwargs)
            if not self._cancelled:
                self.finished.emit()
        except Exception as exc:
            self.error.emit(str(exc))

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

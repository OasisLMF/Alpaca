from contextlib import contextmanager

import logging
import threading

_thread_local = threading.local()


class TargetFilter(logging.Filter):
    """Injects the current thread's target label (see log_target) into every log record.

    Lets alpaca.benchmark.executor tag concurrent EC2 targets' interleaved log output
    (e.g. 'PiWind branch:stable/2.5.x' vs 'PiWind branch:stable/2.4.x') so they're
    distinguishable on the console, without threading a label through every function
    call in the SSH/model-run call stack.
    """

    def filter(self, record):
        """Set record.target to the current thread's label, or '' if none is set.

        Args:
            record: The LogRecord being emitted.

        Returns:
            bool: Always True (never filters out a record).
        """
        target = getattr(_thread_local, "target", None)
        record.target = f" [{target}]" if target else ""
        return True


@contextmanager
def log_target(label):
    """Tag every log record emitted on the current thread with a target label.

    Args:
        label: Short identifier for the current thread's target (e.g.
            'PiWind branch:stable/2.5.x'), shown in every log line via TargetFilter.
    """
    _thread_local.target = label
    try:
        yield
    finally:
        _thread_local.target = None

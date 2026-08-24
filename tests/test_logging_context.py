from alpaca.logging_context import TargetFilter, log_target

import logging
import threading


def _make_record():
    return logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)


def test_target_filter_defaults_to_empty_string_outside_log_target():
    record = _make_record()

    assert TargetFilter().filter(record) is True
    assert record.target == ""


def test_target_filter_shows_label_inside_log_target():
    with log_target("PiWind branch:stable/2.5.x"):
        record = _make_record()
        TargetFilter().filter(record)

    assert record.target == " [PiWind branch:stable/2.5.x]"


def test_log_target_clears_label_on_exit():
    with log_target("PiWind branch:stable/2.5.x"):
        pass

    record = _make_record()
    TargetFilter().filter(record)

    assert record.target == ""


def test_log_target_is_isolated_per_thread():
    seen = {}

    def worker(label):
        with log_target(label):
            record = _make_record()
            TargetFilter().filter(record)
            seen[label] = record.target

    threads = [
        threading.Thread(target=worker, args=("PiWind branch:stable/2.5.x",)),
        threading.Thread(target=worker, args=("PiWind branch:stable/2.4.x",)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seen == {
        "PiWind branch:stable/2.5.x": " [PiWind branch:stable/2.5.x]",
        "PiWind branch:stable/2.4.x": " [PiWind branch:stable/2.4.x]",
    }

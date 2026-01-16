from alpaca.utils import remove_start, _download_results
import pytest
from unittest import mock
from pathlib import Path
import stat
import tempfile


@pytest.mark.parametrize(
    "input_text,expected", [
        ("hello world", "hello world"),
        ("hello INFO- world", "world"),
        ("WARNING- hello world", "hello world"),
        ("hello worERROR-ld", "ld"),
        ("a lot of INFO needs WARNINGs to not ERROR", "a lot of INFO needs WARNINGs to not ERROR")]
)
def test_remove_start(input_text, expected):
    assert remove_start(input_text) == expected


class FakeAttr:
    def __init__(self, filename, st_mode):
        self.filename = filename
        self.st_mode = st_mode


def test_download_results():
    with tempfile.TemporaryDirectory() as d:
        sftp = mock.Mock()

        remote_root = Path("/remote")
        local_root = Path(d) / "results"

        def listdir_side_effect(path):
            if path == "/remote":
                return [
                    FakeAttr("input", stat.S_IFDIR),
                    FakeAttr("fifo", stat.S_IFDIR),
                    FakeAttr("data.csv", stat.S_IFREG),
                    FakeAttr("nested", stat.S_IFDIR),
                ]
            if path == "/remote/input":
                return [
                    FakeAttr("keys.csv", stat.S_IFREG),
                    FakeAttr("ignore.txt", stat.S_IFREG),
                ]
            if path == "/remote/nested":
                return [
                    FakeAttr("nested.txt", stat.S_IFREG),
                ]
            return []

        sftp.listdir_attr.side_effect = listdir_side_effect

        _download_results(sftp, remote_root, local_root)
        assert (local_root / "input").is_dir()
        assert (local_root / "nested").is_dir()

        expected_calls = [
            mock.call("/remote/input/keys.csv", str(local_root / "input" / "keys.csv")),
            mock.call("/remote/data.csv", str(local_root / "data.csv")),
            mock.call("/remote/nested/nested.txt", str(local_root / "nested" / "nested.txt")),
        ]

        sftp.get.assert_has_calls(expected_calls, any_order=True)
        assert sftp.get.call_count == 3

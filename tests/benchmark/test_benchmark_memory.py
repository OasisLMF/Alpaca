from alpaca.benchmark.memory import find_memory_file, format_memory, format_size, memory_warnings, summarise_memory

import os

HEADER = "timestamp,total_kib,used_kib,swap_used_kib,oom_kills\n"


def _write_memory(directory, rows, name="memory.csv"):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(HEADER + "".join(f"{row}\n" for row in rows))
    return path


def test_summarise_memory_reports_the_peak_the_instance_size_and_problems(tmp_path):
    _write_memory(tmp_path, ["1.0,16000000,500000,0,2", "2.0,16000000,9000000,0,2", "3.0,16000000,4000000,2048,3"])

    assert summarise_memory(tmp_path) == {
        "peak_used_kib": 9000000, "total_kib": 16000000, "peak_swap_used_kib": 2048, "oom_kills": 1, "samples": 3,
    }


def test_summarise_memory_skips_the_line_cut_short_when_the_sampler_was_stopped(tmp_path):
    path = _write_memory(tmp_path, ["1.0,16000000,500000,0,0"])
    with open(path, "a") as f:
        f.write("2.0,16000000,90")

    summary = summarise_memory(tmp_path)

    assert summary["samples"] == 1
    assert summary["peak_used_kib"] == 500000


def test_summarise_memory_counts_no_kills_when_the_kernel_does_not_report_them(tmp_path):
    _write_memory(tmp_path, ["1.0,16000000,500000,0,", "2.0,16000000,600000,0,"])

    assert summarise_memory(tmp_path)["oom_kills"] == 0


def test_summarise_memory_is_none_without_samples(tmp_path):
    assert summarise_memory(tmp_path) is None
    _write_memory(tmp_path, [])
    assert summarise_memory(tmp_path) is None


def test_find_memory_file_finds_the_newest_one_at_any_depth(tmp_path):
    old = _write_memory(tmp_path / "old", ["1.0,1,1,0,0"])
    new = _write_memory(tmp_path / "nested" / "runs", ["1.0,1,1,0,0"])
    os.utime(old, (1, 1))

    assert find_memory_file(tmp_path) == new


def test_format_memory_and_size():
    assert format_memory({"peak_used_kib": 9.8 * 1024 ** 2, "total_kib": 15.3 * 1024 ** 2}) == "peak memory 9.8 GiB of 15.3 GiB"
    assert format_size(50 * 1024) == "50 MiB"


def test_memory_warnings_are_empty_for_a_healthy_run():
    assert memory_warnings(None) == []
    assert memory_warnings({"peak_swap_used_kib": 0, "oom_kills": 0}) == []
    assert memory_warnings({"peak_swap_used_kib": 0, "oom_kills": 2}) == [
        "the kernel killed 2 processes for running out of memory"
    ]

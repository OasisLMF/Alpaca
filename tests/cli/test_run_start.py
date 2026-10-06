from alpaca.cli.run_start import run_model, run_pytest, run_api, run_benchmark
import pytest
from unittest import mock


@mock.patch("alpaca.cli.run_start.model_main")
def test_run_model_calls_main_with_config(mock_main):
    """Test that run_model calls model main with config file path."""
    config_path = "config.json"
    run_model([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_h_flag(mock_print, mock_main):
    """Test that run_model prints usage with -h flag."""
    run_model(["-h"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_help_arg(mock_print, mock_main):
    """Test that run_model prints usage with help argument."""
    run_model(["help"])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_model prints usage when no args provided."""
    run_model([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.pytest_main")
def test_run_pytest_calls_main_with_config(mock_main):
    """Test that run_pytest calls pytest main with config file path."""
    config_path = "test_config.json"
    run_pytest([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.pytest_main")
@mock.patch("builtins.print")
def test_run_pytest_prints_help_with_help_flag(mock_print, mock_main):
    """Test that run_pytest prints usage with --help flag."""
    run_pytest(["--help"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.pytest_main")
@mock.patch("builtins.print")
def test_run_pytest_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_pytest prints usage when no args provided."""
    run_pytest([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
def test_run_api_calls_main_with_config(mock_main):
    """Test that run_api calls api main with config file path."""
    config_path = "api_config.json"
    run_api([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_h_flag(mock_print, mock_main):
    """Test that run_api prints usage with h flag."""
    run_api(["h"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_help_hyphen_flag(mock_print, mock_main):
    """Test that run_api prints usage with -help flag."""
    run_api(["-help"])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_api prints usage when no args provided."""
    run_api([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
def test_run_model_with_path_containing_special_chars(mock_main):
    """Test that run_model handles config paths with special characters."""
    config_path = "./configs/my-config.json"
    run_model([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.benchmark_main")
def test_run_benchmark_calls_main_with_config(mock_main):
    """Test that run_benchmark calls benchmark main with config file path."""
    config_path = "benchmark_config.json"
    run_benchmark([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.benchmark_main")
@mock.patch("builtins.print")
def test_run_benchmark_prints_help_with_h_flag(mock_print, mock_main):
    """Test that run_benchmark prints usage with -h flag."""
    run_benchmark(["-h"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.benchmark_main")
@mock.patch("builtins.print")
def test_run_benchmark_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_benchmark prints usage when no args provided."""
    run_benchmark([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.benchmark_main")
def test_run_benchmark_exits_with_status_1_when_a_run_failed(mock_main):
    """A scheduled or CI benchmark mustn't look green when a run failed."""
    mock_main.return_value = {"results": [{"status": "failed"}], "comparison": []}

    with pytest.raises(SystemExit) as exit_info:
        run_benchmark(["benchmark_config.json"])

    assert exit_info.value.code == 1


@mock.patch("alpaca.cli.run_start.benchmark_main")
def test_run_benchmark_exits_with_status_1_when_outputs_differ(mock_main):
    mock_main.return_value = {
        "results": [{"status": "success"}, {"status": "success"}],
        "comparison": [{"group": "PiWind", "report": {"status": "fail"}, "skip_reason": ""}],
    }

    with pytest.raises(SystemExit):
        run_benchmark(["benchmark_config.json"])


@mock.patch("alpaca.cli.run_start.benchmark_main")
def test_run_benchmark_returns_normally_when_everything_passed(mock_main):
    mock_main.return_value = {
        "results": [{"status": "success"}, {"status": "success"}],
        "comparison": [{"group": "PiWind", "report": {"status": "pass"}, "skip_reason": ""}],
    }

    run_benchmark(["benchmark_config.json"])


@mock.patch("alpaca.cli.run_start.benchmark_main")
@mock.patch("builtins.print")
def test_run_benchmark_prints_where_each_failure_txt_is(mock_print, mock_main):
    """The failure evidence is listed at the end of the run rather than left to be found."""
    mock_main.return_value = {
        "results": [
            {"status": "success", "model": "PiWind", "test": "test_1", "version": "2.5.8"},
            {"status": "failed", "model": "PiWind", "test": "test_2", "version": "2.5.8",
             "failure": {"stage": "model run", "message": "boom", "details": "/runs/PiWind-test_2-2.5.8/failure.txt"}},
        ],
        "comparison": [],
        "report_path": "/runs/benchmark_report.txt",
    }

    with pytest.raises(SystemExit):
        run_benchmark(["benchmark_config.json"])

    printed = [call.args[0] for call in mock_print.call_args_list]
    assert "- PiWind test_2 2.5.8: /runs/PiWind-test_2-2.5.8/failure.txt" in printed
    assert "Full report: /runs/benchmark_report.txt" in printed
    assert not any("test_1" in line for line in printed)

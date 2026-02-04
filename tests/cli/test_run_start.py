from alpaca.cli.run_start import run_model, run_pytest, run_api
from unittest import mock


@mock.patch("alpaca.cli.run_start.model_main")
def test_run_model_calls_main_with_config(mock_main):
    """Test that run_model calls model main with config file path"""
    config_path = "config.json"
    run_model([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_h_flag(mock_print, mock_main):
    """Test that run_model prints usage with -h flag"""
    run_model(["-h"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_help_arg(mock_print, mock_main):
    """Test that run_model prints usage with help argument"""
    run_model(["help"])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
@mock.patch("builtins.print")
def test_run_model_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_model prints usage when no args provided"""
    run_model([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.pytest_main")
def test_run_pytest_calls_main_with_config(mock_main):
    """Test that run_pytest calls pytest main with config file path"""
    config_path = "test_config.json"
    run_pytest([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.pytest_main")
@mock.patch("builtins.print")
def test_run_pytest_prints_help_with_help_flag(mock_print, mock_main):
    """Test that run_pytest prints usage with --help flag"""
    run_pytest(["--help"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.pytest_main")
@mock.patch("builtins.print")
def test_run_pytest_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_pytest prints usage when no args provided"""
    run_pytest([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
def test_run_api_calls_main_with_config(mock_main):
    """Test that run_api calls api main with config file path"""
    config_path = "api_config.json"
    run_api([config_path])
    mock_main.assert_called_once_with(config_path)


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_h_flag(mock_print, mock_main):
    """Test that run_api prints usage with h flag"""
    run_api(["h"])
    mock_print.assert_called_once()
    assert "Usage" in mock_print.call_args[0][0]
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_help_hyphen_flag(mock_print, mock_main):
    """Test that run_api prints usage with -help flag"""
    run_api(["-help"])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.api_main")
@mock.patch("builtins.print")
def test_run_api_prints_help_with_no_args(mock_print, mock_main):
    """Test that run_api prints usage when no args provided"""
    run_api([])
    mock_print.assert_called_once()
    mock_main.assert_not_called()


@mock.patch("alpaca.cli.run_start.model_main")
def test_run_model_with_path_containing_special_chars(mock_main):
    """Test that run_model handles config paths with special characters"""
    config_path = "./configs/my-config.json"
    run_model([config_path])
    mock_main.assert_called_once_with(config_path)

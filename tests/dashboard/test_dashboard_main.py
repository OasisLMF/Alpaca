from alpaca.dashboard.main import main
from alpaca.exceptions import OasisAlpacaError

import pytest


EPT_CONTENT = (
    "SummaryId,EPCalc,EPType,ReturnPeriod,Loss\n"
    "1,1,1,200.0,900.0\n"
    "1,1,1,100.0,500.0\n"
    "1,1,2,100.0,999.0\n"
)


def _write_run(tmp_path, filename="gul_S1_ept.csv", content=EPT_CONTENT):
    output_dir = tmp_path / "losses-20260804135955" / "output"
    output_dir.mkdir(parents=True)
    (output_dir / filename).write_text(content)
    return tmp_path


def test_main_writes_a_dashboard_html_file_next_to_the_run(tmp_path):
    run_directory = _write_run(tmp_path)

    dashboard_path = main(run_directory)

    assert dashboard_path == run_directory / "dashboard.html"
    assert dashboard_path.exists()


def test_main_charts_only_the_default_ep_calc_and_type(tmp_path):
    run_directory = _write_run(tmp_path)

    dashboard_path = main(run_directory)

    html_text = dashboard_path.read_text()
    assert "900.0" in html_text
    assert "999.0" not in html_text


def test_main_raises_when_no_output_directory_exists(tmp_path):
    with pytest.raises(OasisAlpacaError):
        main(tmp_path)


def test_main_raises_when_ept_file_is_missing(tmp_path):
    run_directory = _write_run(tmp_path, filename="il_S1_ept.csv")

    with pytest.raises(OasisAlpacaError):
        main(run_directory)

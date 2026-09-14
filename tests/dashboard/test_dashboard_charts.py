from alpaca.dashboard.charts import build_step_chart_data, parse_ept_csv


EPT_HEADER = "SummaryId,EPCalc,EPType,ReturnPeriod,Loss\n"


def _write_ept(path, rows):
    path.write_text(EPT_HEADER + "\n".join(rows) + "\n")


def test_parse_ept_csv_filters_to_the_requested_ep_calc_and_type(tmp_path):
    """Only the requested EPCalc/EPType combination should be read out, since an EPT file
    holds several per SummaryId.
    """
    ept_path = tmp_path / "gul_S1_ept.csv"
    _write_ept(ept_path, [
        "1,1,1,100.0,500.0",
        "1,1,2,100.0,999.0",
        "1,2,1,100.0,111.0",
    ])

    series = parse_ept_csv(ept_path, ep_calc=1, ep_type=1)

    assert series == {1: [(100.0, 500.0)]}


def test_parse_ept_csv_groups_by_summary_id(tmp_path):
    """Each SummaryId is its own loss curve series."""
    ept_path = tmp_path / "gul_S1_ept.csv"
    _write_ept(ept_path, [
        "1,1,1,100.0,500.0",
        "2,1,1,100.0,750.0",
    ])

    series = parse_ept_csv(ept_path)

    assert set(series) == {1, 2}


def test_parse_ept_csv_sorts_each_series_by_return_period_descending(tmp_path):
    """A step chart reads from the rarest event down to the most frequent."""
    ept_path = tmp_path / "gul_S1_ept.csv"
    _write_ept(ept_path, [
        "1,1,1,50.0,200.0",
        "1,1,1,200.0,900.0",
        "1,1,1,100.0,500.0",
    ])

    series = parse_ept_csv(ept_path)

    assert series[1] == [(200.0, 900.0), (100.0, 500.0), (50.0, 200.0)]


def test_build_step_chart_data_builds_one_hv_step_trace_per_summary_id():
    series = {2: [(100.0, 750.0)], 1: [(200.0, 900.0), (100.0, 500.0)]}

    traces = build_step_chart_data(series)

    assert [trace["name"] for trace in traces] == ["Summary 1", "Summary 2"]
    assert traces[0]["x"] == [200.0, 100.0]
    assert traces[0]["y"] == [900.0, 500.0]
    assert traces[0]["line"]["shape"] == "hv"

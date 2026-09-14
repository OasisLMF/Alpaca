from pathlib import Path

import csv

DEFAULT_EP_CALC = 1
DEFAULT_EP_TYPE = 1


def parse_ept_csv(path, ep_calc=DEFAULT_EP_CALC, ep_type=DEFAULT_EP_TYPE):
    """Read an OasisLMF EPT output file into one loss series per SummaryId.

    An EPT file (e.g. 'gul_S1_ept.csv') holds several EPCalc/EPType combinations per
    SummaryId; only the requested combination is read out, since plotting all of them at
    once would be noise rather than a single readable EP curve.

    Args:
        path: Path to the EPT CSV file.
        ep_calc: EPCalc value to filter on (1 = Full Uncertainty).
        ep_type: EPType value to filter on (1 = Occurrence Exceedance Probability).

    Returns:
        dict[int, list[tuple[float, float]]]: SummaryId -> list of (return_period, loss),
            sorted by return_period descending, so a step chart reads from the rarest event
            down to the most frequent.
    """
    series = {}
    with open(Path(path), newline="") as ept_file:
        for row in csv.DictReader(ept_file):
            if int(row["EPCalc"]) != ep_calc or int(row["EPType"]) != ep_type:
                continue
            summary_id = int(row["SummaryId"])
            series.setdefault(summary_id, []).append((float(row["ReturnPeriod"]), float(row["Loss"])))

    for points in series.values():
        points.sort(key=lambda point: point[0], reverse=True)
    return series


def build_step_chart_data(series):
    """Shape an EPT series dict into Plotly scatter traces for a step chart.

    Args:
        series: dict[int, list[tuple[float, float]]] as returned by parse_ept_csv.

    Returns:
        list[dict]: One Plotly trace per SummaryId, ordered by SummaryId, each a
            'scatter' trace with mode 'lines' and shape 'hv' (step chart).
    """
    traces = []
    for summary_id in sorted(series):
        points = series[summary_id]
        traces.append({
            "name": f"Summary {summary_id}",
            "x": [point[0] for point in points],
            "y": [point[1] for point in points],
            "type": "scatter",
            "mode": "lines",
            "line": {"shape": "hv"},
        })
    return traces

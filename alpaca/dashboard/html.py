from pathlib import Path

import json

DASHBOARD_FILENAME = "dashboard.html"
VENDOR_DIR = Path(__file__).parent / "vendor"


def build_dashboard_html(chart_data):
    """Build a single self-contained HTML page for a run's EP curve step chart.

    Plotly.js is inlined into the page (rather than linked, whether to a CDN or a relative
    vendor path) so the resulting file stays self-contained and works fully offline even if
    moved away from the run directory it was generated into.

    Args:
        chart_data: list[dict] of Plotly traces, as returned by build_step_chart_data.

    Returns:
        str: The full HTML document.
    """
    plotly_js = (VENDOR_DIR / "plotly.min.js").read_text()
    traces_json = json.dumps(chart_data)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Alpaca run dashboard</title>
<script>
{plotly_js}
</script>
</head>
<body>
<h1>Simulated loss (EP) curve</h1>
<div id="ep-curve-chart" style="width:100%;height:600px;"></div>
<script>
Plotly.newPlot("ep-curve-chart", {traces_json}, {{
    title: "Occurrence Exceedance Probability (EPCalc=1, EPType=1)",
    xaxis: {{title: "Return Period (years)", type: "log"}},
    yaxis: {{title: "Loss"}},
}});
</script>
</body>
</html>
"""


def write_dashboard(html_text, run_directory):
    """Write the dashboard HTML alongside a run's downloaded results.

    Args:
        html_text: HTML built by build_dashboard_html.
        run_directory: Local directory a run's results were downloaded to.

    Returns:
        Path: Where the dashboard was written.
    """
    dashboard_path = Path(run_directory) / DASHBOARD_FILENAME
    dashboard_path.write_text(html_text)
    return dashboard_path

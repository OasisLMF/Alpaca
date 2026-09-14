from alpaca.benchmark.comparison import find_output_dir
from alpaca.dashboard.charts import build_step_chart_data, parse_ept_csv
from alpaca.dashboard.html import build_dashboard_html, write_dashboard
from alpaca.dashboard.map import parse_location_csv
from alpaca.exceptions import OasisAlpacaError

import logging

logger = logging.getLogger(__name__)

EPT_FILENAME = "gul_S1_ept.csv"
LOCATION_FILENAME = "location.csv"


def main(run_directory):
    """Build a static HTML dashboard for one run's simulated loss (EP) curve.

    Args:
        run_directory: Local directory a model or benchmark target's results were
            downloaded to (the same directory passed to 'alpaca model'/'alpaca benchmark').

    Returns:
        Path: Where the dashboard HTML was written.

    Raises:
        OasisAlpacaError: If no output directory, or no EPT file, is found under
            run_directory.
    """
    output_dir = find_output_dir(run_directory)
    ept_path = output_dir / EPT_FILENAME
    if not ept_path.exists():
        raise OasisAlpacaError(f"No '{EPT_FILENAME}' found in {output_dir}")

    series = parse_ept_csv(ept_path)
    chart_data = build_step_chart_data(series)

    location_path = output_dir.parent / "input" / LOCATION_FILENAME
    map_points = parse_location_csv(location_path) if location_path.exists() else None
    if map_points is None:
        logger.info(f"No '{LOCATION_FILENAME}' found alongside the run, skipping the exposure map")

    html_text = build_dashboard_html(chart_data, map_points)

    dashboard_path = write_dashboard(html_text, run_directory)
    logger.info(f"Dashboard written to {dashboard_path}")
    return dashboard_path

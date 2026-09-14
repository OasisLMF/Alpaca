from pathlib import Path

import json

DASHBOARD_FILENAME = "dashboard.html"
VENDOR_DIR = Path(__file__).parent / "vendor"


def build_dashboard_html(chart_data, map_points=None):
    """Build a single self-contained HTML page for a run's EP curve step chart, and
    optionally an exposure heatmap.

    Every library (Plotly.js, and Leaflet.js/leaflet-heat.js when map_points is given) is
    inlined into the page rather than linked, whether to a CDN or a relative vendor path, so
    the resulting file stays self-contained even if moved away from the run directory it was
    generated into. The one exception is the map's OpenStreetMap basemap tiles: those are
    raster images fetched from tile.openstreetmap.org at view time, which can't be vendored
    without losing pan/zoom, so viewing the map (unlike the chart) still needs internet.

    Args:
        chart_data: list[dict] of Plotly traces, as returned by build_step_chart_data.
        map_points: list[tuple[float, float, float]] of (lat, lon, weight) heatmap points,
            as returned by parse_location_csv, or None/empty to omit the map section
            entirely (e.g. when the run has no location.csv, such as one downloaded before
            it was included).

    Returns:
        str: The full HTML document.
    """
    plotly_js = (VENDOR_DIR / "plotly.min.js").read_text()
    traces_json = json.dumps(chart_data)
    map_section = _build_map_section(map_points) if map_points else ""
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
{map_section}
</body>
</html>
"""


def _build_map_section(map_points):
    """Build the exposure heatmap section of the dashboard.

    Args:
        map_points: list[tuple[float, float, float]] of (lat, lon, weight) heatmap points.

    Returns:
        str: An HTML fragment with the map's own inlined CSS/JS, ready to drop into the
            dashboard body.
    """
    leaflet_css = (VENDOR_DIR / "leaflet.css").read_text()
    leaflet_js = (VENDOR_DIR / "leaflet.js").read_text()
    leaflet_heat_js = (VENDOR_DIR / "leaflet-heat.js").read_text()
    points_json = json.dumps([list(point) for point in map_points])
    center_lat = sum(point[0] for point in map_points) / len(map_points)
    center_lon = sum(point[1] for point in map_points) / len(map_points)
    return f"""<h1>Exposure locations</h1>
<style>
{leaflet_css}
</style>
<script>
{leaflet_js}
</script>
<script>
{leaflet_heat_js}
</script>
<div id="exposure-map" style="width:100%;height:600px;"></div>
<script>
var map = L.map("exposure-map").setView([{center_lat}, {center_lon}], 12);
L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
    attribution: "&copy; OpenStreetMap contributors",
}}).addTo(map);
L.heatLayer({points_json}, {{radius: 20}}).addTo(map);
</script>
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

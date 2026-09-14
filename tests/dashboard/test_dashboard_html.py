from alpaca.dashboard.html import build_dashboard_html, write_dashboard


SAMPLE_TRACES = [
    {"name": "Summary 1", "x": [200.0, 100.0], "y": [900.0, 500.0], "type": "scatter", "mode": "lines", "line": {"shape": "hv"}},
]


def test_build_dashboard_html_inlines_plotly_so_the_page_works_offline():
    """Plotly.js is inlined (not linked to a CDN or a relative vendor path) so the page
    stays self-contained even if moved away from the run directory it was built for.
    """
    html_text = build_dashboard_html(SAMPLE_TRACES)

    assert "<script src=" not in html_text
    assert "Plotly.newPlot" in html_text
    assert "plotly.js" in html_text.lower()


def test_build_dashboard_html_embeds_the_trace_data():
    html_text = build_dashboard_html(SAMPLE_TRACES)

    assert '"name": "Summary 1"' in html_text
    assert "900.0" in html_text and "500.0" in html_text


def test_write_dashboard_writes_alongside_the_run_directory(tmp_path):
    dashboard_path = write_dashboard("<html></html>", tmp_path)

    assert dashboard_path == tmp_path / "dashboard.html"
    assert dashboard_path.read_text() == "<html></html>"


def test_build_dashboard_html_omits_map_section_when_no_points_given():
    """A run downloaded before location.csv was included has no map data to show."""
    html_text = build_dashboard_html(SAMPLE_TRACES, map_points=None)

    assert "exposure-map" not in html_text
    assert "L.heatLayer" not in html_text


def test_build_dashboard_html_includes_inlined_map_when_points_given():
    map_points = [(52.766, -0.895, 220000.0), (52.767, -0.896, 790000.0)]

    html_text = build_dashboard_html(SAMPLE_TRACES, map_points=map_points)

    assert "<script src=" not in html_text
    assert "exposure-map" in html_text
    assert "L.heatLayer" in html_text
    assert "52.766" in html_text and "-0.895" in html_text

from alpaca.dashboard.map import parse_location_csv


LOCATION_HEADER = "LocNumber,Latitude,Longitude,BuildingTIV\n"


def _write_locations(path, rows):
    path.write_text(LOCATION_HEADER + "\n".join(rows) + "\n")


def test_parse_location_csv_reads_lat_lon_and_weight(tmp_path):
    location_path = tmp_path / "location.csv"
    _write_locations(location_path, ["1,52.76698052,-0.895469856,220000.0"])

    points = parse_location_csv(location_path)

    assert points == [(52.76698052, -0.895469856, 220000.0)]


def test_parse_location_csv_defaults_weight_to_one_when_tiv_missing(tmp_path):
    location_path = tmp_path / "location.csv"
    location_path.write_text("LocNumber,Latitude,Longitude\n1,52.0,-0.9\n")

    points = parse_location_csv(location_path)

    assert points == [(52.0, -0.9, 1.0)]


def test_parse_location_csv_reads_every_row(tmp_path):
    location_path = tmp_path / "location.csv"
    _write_locations(location_path, [
        "1,52.766,-0.895,220000.0",
        "2,52.767,-0.896,790000.0",
    ])

    points = parse_location_csv(location_path)

    assert len(points) == 2

from pathlib import Path

import csv

DEFAULT_WEIGHT_FIELD = "BuildingTIV"


def parse_location_csv(path, weight_field=DEFAULT_WEIGHT_FIELD):
    """Read an OED exposure location file into heatmap points.

    Args:
        path: Path to the location CSV file (OED format, with Latitude/Longitude columns).
        weight_field: Column used to weight each point on the heatmap (defaults to
            BuildingTIV, so higher-value locations stand out more). Rows missing or with a
            non-numeric value for this column fall back to a weight of 1.

    Returns:
        list[tuple[float, float, float]]: (latitude, longitude, weight) per location.
    """
    points = []
    with open(Path(path), newline="") as location_file:
        for row in csv.DictReader(location_file):
            try:
                weight = float(row.get(weight_field) or 1)
            except ValueError:
                weight = 1.0
            points.append((float(row["Latitude"]), float(row["Longitude"]), weight))
    return points

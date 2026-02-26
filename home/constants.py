from django.contrib.gis.geos import Point

DATE_INPUT_FORMAT = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%y", "%d/%m/%Y"]

SURVEY_FIELD_VALIDATORS = {
    "max_length": {"email": 250, "text": 700, "text_area": 700, "url": 250},
    "min_length": {"text_area": 1, "text": 1},
}

SRID_WGS84 = 4326  # WGS84 standard (lat/lon coordinates)

# Conventional "unknown location" coordinate (0°N, 0°E, WGS84)
NULL_ISLAND = Point(0, 0, srid=SRID_WGS84)

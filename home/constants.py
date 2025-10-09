DATE_INPUT_FORMAT = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%y", "%d/%m/%Y"]

SURVEY_FIELD_VALIDATORS = {
    "max_length": {"email": 250, "text": 700, "text_area": 700, "url": 250},
    "min_length": {"text_area": 1, "text": 1},
}

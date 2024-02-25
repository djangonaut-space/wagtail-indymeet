DATE_INPUT_FORMAT = ["%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%y", "%d/%m/%Y"]

SURVEY_FIELD_VALIDATORS = {
    "max_length": {"email": 150, "text": 250, "url": 250},
    "min_length": {"text_area": 100, "text": 3},
}

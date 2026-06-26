from django.http import QueryDict
from django.test import TestCase

from home.widgets import TomSelectMultipleWidget


class TomSelectMultipleWidgetTests(TestCase):
    def setUp(self):
        self.widget = TomSelectMultipleWidget()

    def test_template_name(self):
        self.assertEqual(
            self.widget.template_name,
            "django/forms/widgets/tom_select_multiple.html",
        )

    def test_media_css(self):
        self.assertIn("css/tom-select.min.css", self.widget.media._css["all"])

    def test_media_js(self):
        js = self.widget.media._js
        self.assertIn("js/tom-select.complete.min.js", js)
        self.assertIn("js/tom-select-init.js", js)

    def test_build_attrs_adds_tom_select_class(self):
        attrs = self.widget.build_attrs({})
        self.assertIn("tom-select", attrs["class"])

    def test_build_attrs_preserves_existing_class(self):
        attrs = self.widget.build_attrs({"class": "my-widget"})
        self.assertIn("my-widget", attrs["class"])
        self.assertIn("tom-select", attrs["class"])

    def test_value_from_datadict_multiple_params(self):
        data = QueryDict("users=1&users=2")
        self.assertEqual(self.widget.value_from_datadict(data, {}, "users"), ["1", "2"])

    def test_value_from_datadict_comma_separated(self):
        data = QueryDict("users=2,1")
        self.assertEqual(self.widget.value_from_datadict(data, {}, "users"), ["2", "1"])

    def test_value_from_datadict_comma_separated_with_spaces(self):
        data = QueryDict("users=2%2C+1")
        self.assertEqual(self.widget.value_from_datadict(data, {}, "users"), ["2", "1"])

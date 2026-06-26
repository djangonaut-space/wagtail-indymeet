from django import forms


class TomSelectMultipleWidget(forms.SelectMultiple):
    """SelectMultiple widget enhanced with Tom Select for searchable multi-select UI."""

    template_name = "django/forms/widgets/tom_select_multiple.html"

    class Media:
        css = {"all": ("css/tom-select.min.css", "css/tom-select-theme.css")}
        js = ("js/tom-select.complete.min.js", "js/tom-select-init.js")

    def value_from_datadict(self, data, files, name):
        values = data.getlist(name)
        if len(values) == 1 and "," in values[0]:
            values = [v.strip() for v in values[0].split(",")]
        return values

    def build_attrs(self, base_attrs, extra_attrs=None):
        attrs = super().build_attrs(base_attrs, extra_attrs)
        css_class = attrs.get("class", "")
        attrs["class"] = f"{css_class} tom-select".strip()
        return attrs


class CheckboxSelectMultipleSurvey(forms.CheckboxSelectMultiple):
    option_template_name = "home/surveys/widgets/checkbox_option.html"


class RadioSelectSurvey(forms.RadioSelect):
    option_template_name = "home/surveys/widgets/radio_option.html"


class DateSurvey(forms.DateTimeInput):
    template_name = "home/surveys/widgets/datepicker.html"


class RatingSurvey(forms.HiddenInput):
    template_name = "home/surveys/widgets/star_rating.html"
    stars = 8

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        context["widget"]["num_ratings"] = self.num_ratings
        return context

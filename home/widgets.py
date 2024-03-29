from __future__ import annotations

from django import forms


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

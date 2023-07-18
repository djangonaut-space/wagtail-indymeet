from django import forms
from django.db import models
from modelcluster.fields import ParentalKey
from wagtail.admin.edit_handlers import (
    FieldPanel,
    InlinePanel,
)
from django.db.models.fields import EmailField, CharField
from wagtail.core.fields import RichTextField
from wagtail.contrib.forms.models import AbstractForm, AbstractFormField
from wagtail.snippets.models import register_snippet


class TestForm(forms.Form):
    test_input = forms.CharField(max_length=255)


class SignUpField(AbstractFormField):
    page = ParentalKey(
        "SignUpPage", on_delete=models.CASCADE, related_name="form_fields"
    )


@register_snippet
class SignUpPage(AbstractForm):
    template_name = "forms/sign_up.html"
    name = CharField(max_length=255, blank=True)
    email = EmailField(max_length=255, blank=True)
    thank_you_text = RichTextField(blank=True)

    content_panels = AbstractForm.content_panels + [
        FieldPanel("name"),
        InlinePanel("form_fields", label="Form fields"),
        FieldPanel("thank_you_text"),
    ]

    def get_template(self, request):
        return self.template_name

    def get_context_data(self, request):
        context = super(SignUpPage, self).get_context(request)
        print(context)
        return context

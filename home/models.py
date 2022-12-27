from django.db import models
from wagtail.models import Page
from home.forms import SignUpPage
from wagtail.snippets.edit_handlers import SnippetChooserPanel

def sign_up_forms(context):
    return{
        'sign_up_forms': SignUpPage.objects.all(),
        'request': context['request'],
    }

class HomePage(Page):
    content_panels = Page.content_panels + [
        
    ]


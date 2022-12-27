from django.db import models

from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail.models import Page
from wagtail.snippets.edit_handlers import SnippetChooserPanel
from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.core.models import  Orderable
from wagtail.snippets.models import register_snippet

from home.forms import SignUpPage

def sign_up_forms(context):
    return{
        'sign_up_forms': SignUpPage.objects.all(),
        'request': context['request'],
    }

class HomePage(Page):
    content_panels = Page.content_panels + [

    ]



@register_snippet
class Speaker(ClusterableModel):
    bio = models.TextField(verbose_name='bio', blank=True, null=True)
    image = models.ImageField(blank=True, null=True)
    name = models.CharField(max_length=255)

    panels = [
        FieldPanel('name'),
        FieldPanel('image'),
        FieldPanel('bio'),
        InlinePanel('links', label='Link items'),
    ]

    def __str__(self):
        return self.name

class Link(Orderable):
    speaker = ParentalKey("Speaker", related_name="links", on_delete=models.CASCADE)
    name = models.CharField( max_length=255)
    url = models.URLField(max_length=255)

    panels = [
        FieldPanel('name'),
        FieldPanel('url')
    ]
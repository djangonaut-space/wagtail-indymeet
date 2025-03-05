from django.db import models


class ResourceLink(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    permanent = models.BooleanField(default=False)
    path = models.TextField(
        help_text="The relative path for requests to the djangonaut.space web app.",
        unique=True,
    )
    url = models.URLField(help_text="The final URL it directs to.", max_length=2000)

    def __str__(self):
        return self.path

import secrets

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from home.managers import TestimonialQuerySet
from home.models.survey import BaseModel


class Testimonial(BaseModel):
    """
    Represents a testimonial from a user about their session experience.

    Users can share their experiences from sessions they participated in.
    Testimonials require admin approval (is_published) before being displayed publicly.
    """

    title = models.CharField(
        max_length=200,
        help_text=_("A title for your testimonial"),
    )
    text = models.TextField(
        help_text=_("Share your experience from this session"),
    )
    image = models.ImageField(
        upload_to="testimonials/",
        blank=True,
        null=True,
        help_text=_("Optional image to accompany your testimonial"),
    )
    image_description = models.CharField(
        max_length=300,
        blank=True,
        help_text=_("Brief description of the image for accessibility (alt text)"),
    )
    session = models.ForeignKey(
        "home.Session",
        on_delete=models.CASCADE,
        related_name="testimonials",
        help_text=_("The session this testimonial is about"),
    )
    author = models.ForeignKey(
        "accounts.CustomUser",
        on_delete=models.CASCADE,
        related_name="testimonials",
        help_text=_("The author of this testimonial"),
    )
    slug = models.SlugField(
        max_length=225,
        blank=True,
        help_text=_("Auto-generated from title and author ID"),
    )
    is_published = models.BooleanField(
        default=False,
        help_text=_("Only published testimonials are visible on the public page"),
    )

    objects = models.Manager.from_queryset(TestimonialQuerySet)()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "author"],
                name="unique_testimonial_per_session",
            )
        ]

    def __str__(self) -> str:
        return f"{self.title} - {self.author}"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        # Generate slug from author name, title, and random code for uniqueness
        name = self.author.first_name or "anon"
        unique = secrets.token_hex(3)
        self.slug = slugify(f"{name}-{self.title}-{unique}")
        if update_fields is not None and "title" in update_fields:
            update_fields = {"slug"}.union(update_fields)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    def get_absolute_url(self) -> str:
        """Return URL to testimonial list with highlight query parameter."""
        return reverse("testimonial_list") + f"#{self.slug}"

    def get_full_url(self) -> str:
        """Return full URL including the base URL."""
        return settings.BASE_URL + self.get_absolute_url()

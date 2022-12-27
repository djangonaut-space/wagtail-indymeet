from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models
from modelcluster.fields import ParentalKey

from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.core.models import  Orderable



class CustomUser(AbstractUser):
    PARTICIPANT = "Participant"
    MENTOR = "Mentor"
    EXPERT = "Expert"
    PROJECT_OWNER = "Project Owner"
    VOLUNTEER = "Volunteer"
    ORGANIZER = "Organizer"
    MEMBER_ROLES = (
        (PARTICIPANT, "Participant"),
        (MENTOR, "Mentor"),
        (EXPERT, "Expert"),
        (PROJECT_OWNER, "Project Owner"),
        (VOLUNTEER, "Volunteer"),
        (ORGANIZER, "Organizer"),
        )

    ACTIVE = "active"
    INACTIVE = "inactive"

    MEMBER_STATUS = (
        (ACTIVE, "Active"),
        (INACTIVE, "Inactive"),
    )
    member_status = models.CharField(choices=MEMBER_STATUS, default=ACTIVE, max_length=50)
    member_role = models.CharField(choices=MEMBER_ROLES, default=PARTICIPANT, max_length=50)
    pronouns =  models.CharField(max_length=20, blank=True, null=True)
    receiving_newsletter = models.BooleanField(default=False)
    bio = models.TextField(verbose_name='bio', blank=True, null=True)
    bio_image = models.ImageField(blank=True, null=True)

    def __str__(self):
        return self.username


class Link(Orderable):
    member = models.ForeignKey("CustomUser", related_name="links", on_delete=models.CASCADE)
    name = models.CharField( max_length=255)
    url = models.URLField(max_length=255)

class MemberList(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    members = models.ManyToManyField("CustomUser")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active =  models.BooleanField(default=True)

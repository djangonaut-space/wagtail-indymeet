from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db import models

from wagtail.core.models import  Orderable



class CustomUser(AbstractUser):
    pass


class UserProfile(models.Model):
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
    user = models.OneToOneField('CustomUser', on_delete=models.CASCADE, related_name="profile")
    member_status = models.CharField(choices=MEMBER_STATUS, default=ACTIVE, max_length=50)
    member_role = models.CharField(choices=MEMBER_ROLES, default=PARTICIPANT, max_length=50)
    pronouns = models.CharField(max_length=20, blank=True, null=True)
    receiving_newsletter = models.BooleanField(default=False)
    bio = models.TextField(blank=True, null=True)
    bio_image = models.ImageField(blank=True, null=True)
    session_participant = models.BooleanField(default=False)
    recruitment_interest = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username


class Link(Orderable):
    member = models.ForeignKey("UserProfile", related_name="links", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=255)

class MemberList(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    members = models.ManyToManyField("CustomUser", related_name="member_lists")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active =  models.BooleanField(default=True)

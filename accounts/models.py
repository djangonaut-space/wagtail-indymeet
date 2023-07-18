from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.urls import reverse
from django.conf import settings

from wagtail.core.models import Orderable


class CustomUser(AbstractUser):
    pass


class UserProfile(models.Model):
    PARTICIPANT = "Participant"
    SPEAKER = "Speaker"
    MENTOR = "Mentor"
    EXPERT = "Expert"
    PROJECT_OWNER = "Project Owner"
    VOLUNTEER = "Volunteer"
    ORGANIZER = "Organizer"
    MEMBER_ROLES = (
        (PARTICIPANT, "Participant"),
        (SPEAKER, "Speaker"),
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
    user = models.OneToOneField(
        "CustomUser", on_delete=models.CASCADE, related_name="profile"
    )
    member_status = models.CharField(
        choices=MEMBER_STATUS, default=ACTIVE, max_length=50
    )
    member_role = models.CharField(
        choices=MEMBER_ROLES, default=PARTICIPANT, max_length=50
    )
    pronouns = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    bio_image = models.ImageField(blank=True, null=True)
    session_participant = models.BooleanField(default=False)
    recruitment_interest = models.BooleanField(default=False)
    accepted_coc = models.BooleanField(default=False)
    email_confirmed = models.BooleanField(default=False)
    receiving_newsletter = models.BooleanField(default=False)
    receiving_event_updates = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username

    def create_unsubscribe_link(self):
        user_id, token = self.make_token().split(":", 1)
        return settings.BASE_URL + reverse(
            "unsubscribe",
            kwargs={
                "user_id": user_id,
                "token": token,
            },
        )

    def make_token(self):
        return TimestampSigner().sign(self.user.id)

    def check_token(self, token):
        try:
            key = f"{self.user.id}:{token}"
            # Valid for 2 days
            TimestampSigner().unsign(key, max_age=60 * 60 * 48)
        except (BadSignature, SignatureExpired):
            return False
        return True


class Link(Orderable):
    member = models.ForeignKey(
        "UserProfile", related_name="links", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=255)


class MemberList(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    members = models.ManyToManyField("CustomUser", related_name="member_lists")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


"""
    ##################### Signals #######################
"""


@receiver(post_save, sender=CustomUser)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=CustomUser)
def save_profile(sender, instance, **kwargs):
    instance.profile.save()

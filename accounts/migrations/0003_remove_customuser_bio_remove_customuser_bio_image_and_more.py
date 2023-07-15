# Generated by Django 4.1.5 on 2023-01-03 23:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_customuser_bio_customuser_bio_image_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="customuser",
            name="bio",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="bio_image",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="member_role",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="member_status",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="pronouns",
        ),
        migrations.RemoveField(
            model_name="customuser",
            name="receiving_newsletter",
        ),
        migrations.AlterField(
            model_name="memberlist",
            name="members",
            field=models.ManyToManyField(
                related_name="member_lists", to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "member_status",
                    models.CharField(
                        choices=[("active", "Active"), ("inactive", "Inactive")],
                        default="active",
                        max_length=50,
                    ),
                ),
                (
                    "member_role",
                    models.CharField(
                        choices=[
                            ("Participant", "Participant"),
                            ("Mentor", "Mentor"),
                            ("Expert", "Expert"),
                            ("Project Owner", "Project Owner"),
                            ("Volunteer", "Volunteer"),
                            ("Organizer", "Organizer"),
                        ],
                        default="Participant",
                        max_length=50,
                    ),
                ),
                ("pronouns", models.CharField(blank=True, max_length=20, null=True)),
                ("receiving_newsletter", models.BooleanField(default=False)),
                ("bio", models.TextField(blank=True, null=True)),
                ("bio_image", models.ImageField(blank=True, null=True, upload_to="")),
                ("session_participant", models.BooleanField(default=False)),
                ("recruitment_interest", models.BooleanField(default=False)),
                ("accepted_coc", models.BooleanField(default=False)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="link",
            name="member",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="links",
                to="accounts.userprofile",
            ),
        ),
    ]

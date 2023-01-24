# Generated by Django 4.1.5 on 2023-01-06 17:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_remove_customuser_bio_remove_customuser_bio_image_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='member_role',
            field=models.CharField(choices=[('Participant', 'Participant'), ('Speaker', 'Speaker'), ('Mentor', 'Mentor'), ('Expert', 'Expert'), ('Project Owner', 'Project Owner'), ('Volunteer', 'Volunteer'), ('Organizer', 'Organizer')], default='Participant', max_length=50),
        ),
    ]
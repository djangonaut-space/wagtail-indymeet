# Generated by Django 4.1.5 on 2023-01-06 19:24

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('home', '0005_remove_speakerlink_speaker_delete_speaker_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=25)),
            ],
        ),
        migrations.CreateModel(
            name='Session',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('start_date', models.DateField()),
                ('end_date', models.DateField()),
                ('title', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('participants', models.ManyToManyField(blank=True, null=True, related_name='sessions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('cover_image', models.ImageField(blank=True, null=True, upload_to='')),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('location', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True, null=True)),
                ('status', models.CharField(choices=[('Pending', 'Pending'), ('Scheduled', 'Scheduled'), ('Canceled', 'Canceled'), ('Rescheduled', 'Rescheduled')], default='Pending', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('capacity', models.IntegerField(blank=True, null=True)),
                ('categories', models.ManyToManyField(blank=True, null=True, related_name='events', to='home.category')),
                ('organizers', models.ManyToManyField(blank=True, null=True, to=settings.AUTH_USER_MODEL)),
                ('rsvped_members', models.ManyToManyField(blank=True, null=True, related_name='rsvp_events', to=settings.AUTH_USER_MODEL)),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='events', to='home.session')),
                ('speakers', models.ManyToManyField(blank=True, null=True, related_name='speaker_events', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('start_time',),
            },
        ),
    ]

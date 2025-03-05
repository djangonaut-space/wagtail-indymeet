from django.db import models
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Survey(BaseModel):
    name = models.CharField(max_length=200)
    description = models.TextField(default="")
    slug = models.SlugField(max_length=225, default="")
    editable = models.BooleanField(
        default=True, help_text=_("If False, user can't edit record.")
    )
    deletable = models.BooleanField(
        default=True, help_text=_("If False, user can't delete record.")
    )
    session = models.ForeignKey(
        "home.Session", on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        return self.name

    def get_survey_response_url(self):
        return reverse("survey_response_create", kwargs={"slug": self.slug})

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        self.slug = slugify(self.name)
        if update_fields is not None and "name" in update_fields:
            update_fields = {"slug"}.union(update_fields)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )


class TypeField(models.TextChoices):
    TEXT = "TEXT", _("Text")
    NUMBER = "NUMBER", _("Number")
    DATE = "DATE", _("Date")
    RADIO = "RADIO", _("Radio")
    SELECT = "SELECT", _("Select")
    MULTI_SELECT = "MULTI_SELECT", _("Multi Select")
    TEXT_AREA = "TEXT_AREA", _("Text Area")
    URL = "URL", _("URL")
    EMAIL = "EMAIL", _("Email")
    RATING = "RATING", _("Rating")


class Question(BaseModel):
    key = models.CharField(
        max_length=500,
        unique=True,
        blank=True,
        help_text=_(
            "Unique key for this question, fill in the blank if "
            "you want to use for automatic generation."
        ),
    )
    survey = models.ForeignKey(
        Survey, related_name="questions", on_delete=models.CASCADE
    )
    label = models.CharField(
        max_length=500, help_text=_("Enter your question in here.")
    )
    type_field = models.CharField(choices=TypeField.choices, max_length=100)
    choices = models.TextField(
        blank=True,
        help_text=_(
            "If type field is radio, select, or multi select, fill in the options separated "
            "by commas. Ex: Male, Female.<br/>"
            "If type field is rating, use a number such as 5."
        ),
    )
    help_text = models.TextField(
        blank=True,
        help_text=_("You can add a help text in here."),
    )
    required = models.BooleanField(
        default=True,
        help_text=_("If True, the user must provide an answer to this question."),
    )
    ordering = models.PositiveIntegerField(
        default=0, help_text=_("Defines the question order within the surveys.")
    )

    class Meta:
        ordering = ["ordering"]

    def __str__(self):
        return f"{self.label}-survey-{self.survey.id}"

    def save(
        self, force_insert=False, force_update=False, using=None, update_fields=None
    ):
        self.key = slugify(self.label)
        if update_fields is not None and "label" in update_fields:
            update_fields = {"key"}.union(update_fields)
        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )


class UserSurveyResponse(BaseModel):
    survey = models.ForeignKey(Survey, on_delete=models.CASCADE)
    user = models.ForeignKey("accounts.CustomUser", on_delete=models.CASCADE)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return str(self.id)


class UserQuestionResponse(BaseModel):
    question = models.ForeignKey(
        Question, related_name="responses", on_delete=models.CASCADE
    )
    value = models.TextField(help_text=_("The value of the answer given by the user."))
    user_survey_response = models.ForeignKey(
        UserSurveyResponse, on_delete=models.CASCADE
    )

    class Meta:
        ordering = ["question__ordering"]

    def __str__(self):
        return f"{self.question}: {self.value}"

    @property
    def get_value(self):
        if self.question.type_field == TypeField.RATING:
            active_star = int(self.value)
            num_stars = int(self.question.choices)
            inactive_star = num_stars - active_star
            elements = [
                f'<div class="flex content-center" id="parent_start_{self.question_id}">'
            ]
            for _ in range(int(active_star)):
                elements.append('<i class ="rating__star rating_active"> </i>')
            for _ in range(inactive_star):
                elements.append('<i class ="rating__star rating_inactive"> </i>')
            elements.append("</div>")
            return mark_safe("".join(elements))
        elif self.question.type_field == TypeField.URL:
            return mark_safe(f'<a href="{self.value}" target="_blank">{self.value}</a>')
        return self.value

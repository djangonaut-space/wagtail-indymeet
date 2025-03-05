from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


class RatingValidator:
    def __init__(self, max):
        self.max = max

    def __call__(self, value):
        try:
            rating = int(value)
        except (TypeError, ValueError):
            raise ValidationError(_("%s is not a number." % value))

        if rating > self.max:
            raise ValidationError(
                _("Value cannot be greater than maximum allowed number of ratings.")
            )

        if rating < 1:
            raise ValidationError(_("Value cannot be less than 1."))

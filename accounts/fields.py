from django.db.models.fields import related


class ReverseDefaultOneToOneDescriptor(related.ReverseOneToOneDescriptor):
    """Avoid accessor errors for a reverse OneToOne descriptor."""

    def __get__(self, instance, cls=None):
        try:
            return super().__get__(instance, cls=cls)
        except self.RelatedObjectDoesNotExist:
            if self.related.field.create is None:
                raise  # Same behavior as OneToOneField
            elif self.related.field.create:
                # We already know that the instance does not exist, but
                # using get_or_create allows us to avoid additional code
                # branches at the expense of making an additional query
                # to check for the existence of the object already.
                rel_obj, _ = self.get_queryset(instance=instance).get_or_create(
                    **{
                        lh_field.attname: getattr(instance, rh_field.attname)
                        for lh_field, rh_field in self.related.field.related_fields
                    }
                )

                # Set the forward accessor cache on the related object to
                # the current instance to avoid an extra SQL query if it's
                # accessed later on.
                self.related.field.set_cached_value(rel_obj, instance)
                self.related.set_cached_value(instance, rel_obj)

                return rel_obj


class DefaultOneToOneField(related.OneToOneField):
    """A OneToOneField that can avoid errors in the reverse relation.

    The ``create`` parameter on the constructor is used to automatically
    create the instance if it doesnt exist when it is accessed via the
    related accessor. If ``created`` is set to ``False`` explicitly, then
    ``None`` will be returned if the related object does not exist.
    """

    related_accessor_class = ReverseDefaultOneToOneDescriptor

    def __init__(self, *args, create=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.create = create

    def deconstruct(self):
        """Deconstruct this field for generating migrations."""
        name, path, args, kwargs = super().deconstruct()
        if self.create is not None:
            kwargs["create"] = self.create
        return name, path, args, kwargs

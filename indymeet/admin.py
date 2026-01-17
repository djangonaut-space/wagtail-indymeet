class DescriptiveSearchMixin:
    """
    Add the verbose model and field names to the search help text.

    This will include the model and field name for each search field.
    If a relationship is more than one related model, it will only display
    the last model of the relationship.

    If a ModelAdmin class has a value for search_help_text, the descriptive
    search text will not be added.

    Source: https://www.better-simple.com/django/2023/08/18/descriptive-django-admin-search/
    """

    def get_search_fields(self, request):
        """
        Override get_search_fields to dynamically set search_help_text

        This is potentially problematic if you're doing something more complicated
        with the admin already. In my case the search functionality is vanilla so this
        works.
        """
        search_fields = super().get_search_fields(request)
        if search_fields and self.search_help_text is None:
            field_strings = []
            for search_field in search_fields:
                current_model_meta = self.model._meta
                if "__" in search_field:
                    field_path = search_field.split("__")
                    # Follow the relationships down to the last path.
                    for path in field_path:
                        field = current_model_meta.get_field(path)
                        if not getattr(field, "related_model"):
                            break
                        current_model_meta = field.related_model._meta
                else:
                    field = current_model_meta.get_field(search_field)
                # Include the human-readable version of the model and field name.
                field_strings.append(
                    f"{current_model_meta.verbose_name.title()}'s {field.verbose_name.title()}"
                )
            self.search_help_text = f'Search by: {", ".join(field_strings)}'
        return search_fields

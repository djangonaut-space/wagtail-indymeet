"""
Custom database lookups for PostgreSQL-specific operations.

This module provides custom lookups that leverage PostgreSQL's advanced
array and JSON operations for efficient querying.
"""

from django.contrib.postgres.lookups import PostgresOperatorLookup
from django.db.models.fields.json import JSONField


@JSONField.register_lookup
class HasOverlap(PostgresOperatorLookup):
    """
    Custom lookup to check if a JSONField array has any overlapping elements
    with another array using PostgreSQL's && (overlap) operator.

    Usage:
        UserAvailability.objects.filter(slots__has_overlap=[24.0, 24.5, 25.0])

    This converts the JSONB array to a PostgreSQL array and uses the && operator
    which returns true if the arrays share any common elements.

    Inherits from PostgresOperatorLookup which provides the framework for
    PostgreSQL-specific operators.
    """

    lookup_name = "has_overlap"
    postgres_operator = "&&"

    def process_lhs(self, compiler, connection):
        """Process the left-hand side (the database field) with type conversion."""
        lhs, lhs_params = super().process_lhs(compiler, connection)
        # Convert JSONB to array
        lhs = f"ARRAY(SELECT jsonb_array_elements_text({lhs})::float)"
        return lhs, lhs_params

"""Resource-related views."""

from django.shortcuts import get_object_or_404, redirect

from home.models import ResourceLink


def resource_link(request, path):
    """Redirect to a resource by its path."""
    return redirect(get_object_or_404(ResourceLink, path=path).url)

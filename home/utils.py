from django.http import HttpRequest
from django.utils.safestring import mark_safe


def get_client_ip(request: HttpRequest) -> str | None:
    """
    Best-effort extraction of the client's IP address from a request.

    Prefers the leftmost address in X-Forwarded-For, since the app runs
    behind a reverse proxy in production, falling back to REMOTE_ADDR.
    """
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def create_star(active_star: int, num_stars: int = 5, id_element: str = "") -> str:
    inactive_star = num_stars - active_star
    elements = [f'<div class="flex content-center" id="parent_start_{id_element}">']
    for _ in range(int(active_star)):
        elements.append('<i class ="rating__star rating_active"> </i>')
    for _ in range(inactive_star):
        elements.append('<i class ="rating__star rating_inactive"> </i>')
    elements.append("</div>")
    return mark_safe("".join(elements))

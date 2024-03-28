from __future__ import annotations

from django.utils.safestring import mark_safe


def create_star(active_star: int, num_stars: int = 5, id_element: str = "") -> str:
    inactive_star = num_stars - active_star
    elements = [f'<div class="flex content-center" id="parent_start_{id_element}">']
    for _ in range(int(active_star)):
        elements.append('<i class ="rating__star rating_active"> </i>')
    for _ in range(inactive_star):
        elements.append('<i class ="rating__star rating_inactive"> </i>')
    elements.append("</div>")
    return mark_safe("".join(elements))

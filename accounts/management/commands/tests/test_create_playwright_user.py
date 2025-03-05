import os

import pytest
from django.contrib.auth import get_user_model
from django.core import management

User = get_user_model()


@pytest.mark.django_db
def test_user_created():
    os.environ["PLAYWRIGHT_TEST_USERNAME"] = "test123"
    os.environ["PLAYWRIGHT_TEST_PASSWORD"] = "test123"
    management.call_command("create_playwright_user")
    user = User.objects.get(username="test123")
    assert user.check_password("test123")
    assert list(user.groups.values_list("name", flat=True)) == ["Editors"]

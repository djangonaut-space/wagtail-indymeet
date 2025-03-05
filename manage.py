#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    # If we're running tests, default to the test settings file
    default_settings = (
        "indymeet.settings.test" if "test" in sys.argv else "indymeet.settings.dev"
    )

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)

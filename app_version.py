"""Single source of truth for the app name and version.

Every module that shows the name or version imports from here, so a
release bump is one line in this file plus a matching git tag.
Never hardcode the version anywhere else.
"""

__version__ = "2.4.1"
APP_NAME = "Lite Tutorial Maker"
APP_DISPLAY_NAME = f"{APP_NAME} v{__version__}"

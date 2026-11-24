"""Vercel loads this module. Run the app locally with `python -m hearthline`."""

from hearthline.wsgi import app

__all__ = ["app"]

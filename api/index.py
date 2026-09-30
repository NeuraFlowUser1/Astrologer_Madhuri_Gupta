"""Sarsa's native Vercel Python function; no legacy backend side effects."""

import os

from backend.booking_engine.hosting import create_hosted_application

app = create_hosted_application(os.environ)

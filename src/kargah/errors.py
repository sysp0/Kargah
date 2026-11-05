"""Typed errors of the new engine."""


class KargahError(Exception):
    """Base class of every error Kargah raises on purpose."""


class TrackerError(KargahError):
    """The ticket tracker refused or failed a call."""

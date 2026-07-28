"""Typed, user-facing errors."""


class YtsError(Exception):
    """An expected failure with a concise message suitable for CLI users."""


class InputError(YtsError):
    pass


class FetchError(YtsError):
    pass


class WriterError(YtsError):
    pass


class OutputError(YtsError):
    pass

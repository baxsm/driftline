class SequenceUnreadable(Exception):
    """A path is not a readable sequence.

    `missing` names the file or directory that was expected, so the API can tell the user
    what to fix instead of returning a generic failure.
    """

    def __init__(self, message: str, missing: str) -> None:
        super().__init__(message)
        self.message = message
        self.missing = missing

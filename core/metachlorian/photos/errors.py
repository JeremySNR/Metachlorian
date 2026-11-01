class PhotoError(ValueError):
    """An actionable photo operation failure, safe to show to a client."""


class LightroomUnavailable(PhotoError):
    def __init__(self, message: str, code: str = 'unavailable'):
        super().__init__(message)
        self.code = code


class PhotoConflict(PhotoError):
    pass


class CacheBudgetExceeded(PhotoError):
    pass

class PhotoError(ValueError):
    """An actionable photo operation failure, safe to show to a client."""


class LightroomUnavailable(PhotoError):
    pass


class PhotoConflict(PhotoError):
    pass


class CacheBudgetExceeded(PhotoError):
    pass

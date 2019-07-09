from typing import Any, Optional


class StompError(Exception):
    def __init__(self, message: Optional[str], detail: Any):
        super().__init__(message)
        self.detail = detail


class StompDisconnectedError(Exception):
    pass


class ExceededRetryCount(Exception):
    def __init__(self, ref: Any):
        super().__init__("Retry count exceeded!")
        self.ref = ref

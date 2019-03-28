
class StompError(Exception):

    def __init__(self, message, detail):
        super(StompError, self).__init__(message)
        self.detail = detail


class StompDisconnectedError(Exception):
    pass


class ExceededRetryCount(Exception):

    def __init__(self, ref):
        super().__init__('Retry count exceeded!')
        self.ref = ref

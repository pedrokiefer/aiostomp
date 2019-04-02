class Subscription(object):

    def __init__(self, destination, id, ack, extra_headers, handler, auto_ack=True):
        self.destination = destination
        self.id = id
        self.ack = ack
        self.extra_headers = extra_headers
        self.handler = handler
        self.auto_ack = auto_ack

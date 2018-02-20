class Frame(object):

    def __init__(self, command, headers, body):
        self.command = command
        self.headers = headers
        self.body = body

    def __repr__(self):
        headers = ''
        if self.headers:
            headers = ';'.join(["%s: %s" % (key, value) for key, value in self.headers.items()])
        return '<Frame: %s headers: %s>' % (self.command, headers)

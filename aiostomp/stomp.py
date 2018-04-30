NULL = b'\x00'
NEWLINE = b'\n'


class Commands:
    CONNECT = 'CONNECT'
    SEND = 'SEND'
    DISCONNECT = 'DISCONNECT'
    SUBSCRIBE = 'SUBSCRIBE'
    UNSUBSCRIBE = 'UNSUBSCRIBE'
    BEGIN = 'BEGIN'
    COMMIT = 'COMMIT'
    ABORT = 'ABORT'
    ACK = 'ACK'

    # Version 1.1
    NACK = 'NACK'
    STOMP = 'STOMP'


class Responses:
    CONNECTED = 'CONNECTED'
    ERROR = 'ERROR'
    MESSAGE = 'MESSAGE'
    RECEIPT = 'RECEIPT'

    HEARTBEAT = 'HEARTBEAT'


class Headers:
    SEPARATOR = ':'
    RECEIPT_REQUEST = 'receipt'
    TRANSACTION = 'transaction'
    CONTENT_LENGTH = 'content-length'
    ACCEPT_VERSION = 'accept-version'
    CONTENT_TYPE = 'content-type'

    class Response:
        RECEIPT_ID = 'receipt-id'

    class Send:
        DESTINATION = 'destination'
        DESTINATION_TYPE = 'destination-type'
        CORRELATION_ID = 'correlation-id'
        REPLY_TO = 'reply-to'
        EXPIRES = 'expires'
        PRIORITY = 'priority'
        TYPE = 'type'
        PERSISTENT = 'persistent'

    class Message:
        MESSAGE_ID = 'message-id'
        DESTINATION = 'destination'
        CORRELATION_ID = 'correlation-id'
        EXPIRES = 'expires'
        REPLY_TO = 'reply-to'
        PRIORITY = 'priority'
        REDELIVERED = 'redelivered'
        TIMESTAMP = 'timestamp'
        TYPE = 'type'
        SUBSCRIPTION = 'subscription'
        ACK = 'ack'
        PERSISTENT = 'persistent'

    class Subscribe:
        DESTINATION = 'destination'
        ACK_MODE = 'ack'
        ID = 'id'
        SELECTOR = 'selector'
        DURABLE_SUBSCRIPTION_NAME = 'durable-subscription-name'
        SUBSCRIPTION_TYPE = 'subscription-type'
        NO_LOCAL = 'no-local'

        class AckModes:
            AUTO = 'auto'
            CLIENT = 'client'
            CLIENT_INDIVIDUAL = 'client-individual'

    class Unsubscribe:
        DESTINATION = 'destination'
        ID = 'id'
        DURABLE_SUBSCRIPTION_NAME = 'durable-subscription-name'

    class Connect:
        LOGIN = 'login'
        PASSCODE = 'passcode'
        CLIENT_ID = 'client-id'
        REQUEST_ID = 'request-id'

        # Version 1.1
        ACCEPT_VERSION = 'accept-version'
        HOST = 'host'
        HEART_BEAT = 'heart-beat'

    class Error:
        MESSAGE = 'message'
        VERSION = 'version'

    class Connected:
        SESSION = 'session'
        RESPONSE_ID = 'response-id'

        # Version 1.1
        VERSION = 'version'
        SERVER = 'server'
        HEART_BEAT = 'heart-beat'

    class Ack:
        MESSAGE_ID = 'message-id'

        # Version 1.1
        SUBSCRIPTION = 'subscription'

        # Version 1.2
        ID = 'id'

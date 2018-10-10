class OP:
    """Gateway OP codes."""
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    STATUS_UPDATE = 3

    # voice connection / disconnection
    VOICE_UPDATE = 4
    VOICE_PING = 5

    RESUME = 6
    RECONNECT = 7
    REQ_GUILD_MEMBERS = 8
    INVALID_SESSION = 9

    HELLO = 10
    HEARTBEAT_ACK = 11

    # request member / presence information
    GUILD_SYNC = 12

    # request to sync up call dm / group dm
    CALL_SYNC = 13

    # request for lazy guilds
    LAZY_REQUEST = 14

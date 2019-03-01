# Litecord Voice Server Protocol (LVSP)

LVSP is a protocol for Litecord to communicate with an external component
dedicated for voice data. The voice server is responsible for the
Voice Websocket Discord and Voice UDP connections.

LVSP runs over a *long-lived* websocket with TLS. The encoding is JSON.

**TODO:** common logic scenarios:
 - initializing a voice channel
 - updating a voice channel
 - destroying a voice channel
 - user joining to a voice channel
 - user joining to a voice channel (while also initializing it, e.g
    first member in the channel)
 - user leaving a voice channel

## OP code table

"client" is litecord. "server" is the voice server.

| opcode | name | sent by |
| --: | :-- | :-- |
| 0 | HELLO | server |
| 1 | IDENTIFY | client |
| 2 | RESUME | client |
| 3 | READY | server |
| 4 | HEARTBEAT | client |
| 5 | HEARTBEAT\_ACK | server |
| 6 | INFO | client / server |
| 7 | VST\_REQUEST | client |

## Message structure

Message data is defined by each opcode.

**Note:** the `snowflake` type follows the same rules as the Discord Gateway's
snowflake type: A string encoding a Discord Snowflake.

| field | type | description |
| --: | :-- | :-- |
| op | integer, opcode | operator code | 
| d | map[string, any] | message data |

## High level overview

 - connect, receive HELLO
 - send IDENTIFY or RESUME
 - if RESUME, process incoming messages as they were post-ready
 - receive READY
 - start HEARTBEAT'ing
 - send INFO / VSU\_REQUEST messages as needed

## Error codes

| code | meaning | 
| --: | :-- |
| 4000 | general error. Reconnect |
| 4001 | authentication failure |
| 4002 | decode error, given message failed to decode as json |

## HELLO message

Sent by the server when a connection is established.

| field | type | description |
| --: | :-- | :-- |
| heartbeat\_interval | integer | amount of milliseconds to heartbeat with |
| nonce | string | random 10-character string used in authentication |

## IDENTIFY message

Sent by the client to identify itself.

| field | type | description |
| --: | :-- | :-- |
| token | string | `HMAC(SHA256, key=[secret shared between server and client]), message=[nonce from HELLO]` |

## RESUME message

Sent by the client to resume itself from a failed websocket connection.

The server will resend its data, then send a READY message.

| field | type | description |
| --: | :-- | :-- |
| token | string | same value from IDENTIFY.token |
| seq | integer | last sequence number to resume from |

## READY message

**TODO:** does READY need any information?

| field | type | description |
| --: | :-- | :-- |

## HEARTBEAT message

Sent by the client as a keepalive / health monitoring method.

The server MUST reply with a HEARTBEAT\_ACK message back in a reasonable
time period.

**TODO:** specify sequence numbers in INFO messages

| field | type | description |
| --: | :-- | :-- |
| s | integer | sequence number |

## HEARTBEAT\_ACK message

Sent by the server in reply to a HEARTBEAT message coming from the client.

**TODO:** add sequence numbers to ACK

| field | type | description |
| --: | :-- | :-- |
| s | integer | sequence number |

## INFO message

Sent by either client or server on creation of update of a given object (
such as a channel's bitrate setting or a user joining a channel).

| field | type | description |
| --: | :-- | :-- |
| type | InfoType | info type |
| info | Union[ChannelInfo, VoiceInfo] | info object |

### IntoType Enum

| value | name | description |
| --: | :-- | :-- |
| 0 | CHANNEL | channel information |
| 1 | VST | Voice State |

### ChannelInfo object

| field | type | description |
| --: | :-- | :-- |
| id | snowflake | channel id |
| bitrate | integer | channel bitrate |

### VoiceInfo object

| field | type | description |
| --: | :-- | :-- |
| user\_id | snowflake | user id |
| channel\_id | snowflake | channel id |
| session\_id | string | session id |
| deaf | boolean | deaf status |
| mute | boolean | mute status |
| self\_deaf | boolean | self-deaf status |
| self\_mute | boolean | self-mute status |
| suppress | boolean | supress status |

## VST\_REQUEST message

Sent by the client to request the creation of a voice state in the voice server.

**TODO:** verify correctness of this behavior.

**TODO:** add logic on client connection

The server SHALL send an INFO message containing the respective VoiceInfo data.

| field | type | description |
| --: | :-- | :-- |
| user\_id | snowflake | user id for the voice state |
| channel\_id | snowflake | channel id for the voice state |

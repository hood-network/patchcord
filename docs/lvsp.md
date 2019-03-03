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

## Message structure

Message data is defined by each opcode.

**Note:** the `snowflake` type follows the same rules as the Discord Gateway's
snowflake type: A string encoding a Discord Snowflake.

| field | type | description |
| --: | :-- | :-- |
| op | integer, opcode | operator code | 
| d | map[string, any] | message data |
| s | Optional[int] | sequence number |

 - The `s` field is explained in the `RESUME` message.

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

### Sequence numbers

Sequence numbers are used to resume a failed connection back and make the
voice server replay its missing events to the client.

They are **positive** integers, **starting from 0.** There is no default
upper limit. A "long int" type in languages will probably be enough for most
use cases.

Replayable messages MUST have sequence numbers embedded into the message
itself with a `s` field. The field lives at the root of the message, alongside
`op` and `d`.

## READY message

 - The `health` field is described with more detail in the `HEARTBEAT_ACK`
    message.

| field | type | description |
| --: | :-- | :-- |
| `health` | Health | server health |

## HEARTBEAT message

Sent by the client as a keepalive / health monitoring method.

The server MUST reply with a HEARTBEAT\_ACK message back in a reasonable
time period.

| field | type | description |
| --: | :-- | :-- |
| s | integer | sequence number |

## HEARTBEAT\_ACK message

Sent by the server in reply to a HEARTBEAT message coming from the client.

The `health` field is a measure of the servers's overall health. It is a
float going from 0 to 1, where 0 is the worst health possible, and 1 is the
best health possible.

Servers SHOULD use the same algorithm to determine health, it CAN be based off:
 - Machine resource usage (RAM, CPU, etc), however they're too general and can
    be unreliable.
 - Total users connected.
 - Total bandwidth used in some X amount of time.

Among others.

| field | type | description |
| --: | :-- | :-- |
| s | integer | sequence number |
| health | float | server health |

## INFO message

Sent by either client or a server to send information between eachother.
The INFO message is extensible in which many request / response scenarios
are laid on.

| field | type | description |
| --: | :-- | :-- |
| type | InfoType | info type |
| data | Any | info data, varies depending on InfoType |

### InfoType Enum

| value | name | description |
| --: | :-- | :-- |
| 0 | CHANNEL\_REQ | channel assignment request |
| 1 | CHANNEL\_ASSIGN | channel assignment reply |
| 2 | CHANNEL\_UPDATE | channel update |
| 3 | CHANNEL\_DESTROY | channel destroy |
| 4 | VST\_CREATE | voice state create request |
| 5 | VST\_UPDATE | voice state update |
| 6 | VST\_LEAVE | voice state leave |

**TODO:** finish all infos

### CHANNEL\_REQ

Request a channel to be created inside the voice server.

The Server MUST reply back with a CHANNEL\_ASSIGN when resources are
allocated for the channel.

**TODO:** fields

### CHANNEL\_ASSIGN

Sent by the Server to signal the successful creation of a voice channel.

**TODO:** fields

### CHANNEL\_UPDATE

Sent by the client to signal an update to the properties of a channel,
such as its bitrate.

**TODO:** fields

### CHANNEL\_DESTROY

Sent by the client to signal the destruction of a voice channel. Be it
a channel being deleted, or all members in it leaving.

**TODO:** fields

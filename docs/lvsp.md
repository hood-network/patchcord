# Litecord Voice Server Protocol (LVSP)

LVSP is a protocol for Litecord to communicate with an external component
dedicated for voice data. The voice server is responsible for the
Voice Websocket Discord and Voice UDP connections.

LVSP runs over a *long-lived* websocket with TLS. The encoding is JSON.

## OP code table

"client" is litecord. "server" is the voice server. 

note: only the opcode is sent in a message, so the names are determined by the implementation of LVSP.

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

## High level overview

 - connect, receive HELLO
 - send IDENTIFY or RESUME
 - if RESUME, process incoming messages as they were post-ready
 - receive READY
 - start HEARTBEAT'ing
 - send INFO messages as needed

## Error codes

| code | meaning | 
| --: | :-- |
| 4000 | general error. reconnect |
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

There are no other fields in this message.

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
| health | float | server health |

## INFO message

Sent by either client or a server to send information between eachother.
The INFO message is extensible in which many request / response scenarios
are laid on.

*This message type MUST be replayable.*

| field | type | description |
| --: | :-- | :-- |
| type | InfoType | info type |
| data | Any | info data, varies depending on InfoType |

### InfoType Enum

note: this enum is only ever identified by its opcode, so the `name` field can differ from the values in this enum without error. 

| value | name | description |
| --: | :-- | :-- |
| 0 | CHANNEL\_REQ | channel assignment request |
| 1 | CHANNEL\_ASSIGN | channel assignment reply |
| 2 | CHANNEL\_DESTROY | channel destroy |
| 3 | VOICE\_STATE\_CREATE | voice state create request |
| 4 | VOICE\_STATE\_DONE | voice state created |
| 5 | VOICE\_STATE\_DESTROY | voice state destroy |
| 6 | VOICE\_STATE\_UPDATE | voice state update |

### CHANNEL\_REQ

Request a channel to be created inside the voice server.

The Server MUST reply back with a CHANNEL\_ASSIGN when resources are
allocated for the channel.

| field | type | description |
| --: | :-- | :-- |
| channel\_id | snowflake | channel id |
| guild\_id | Optional[snowflake] | guild id, not provided if dm / group dm |

### CHANNEL\_ASSIGN

Sent by the Server to signal the successful creation of a voice channel.

| field | type | description |
| --: | :-- | :-- |
| channel\_id | snowflake | channel id |
| guild\_id | Optional[snowflake] | guild id, not provided if dm / group dm |
| token | string | authentication token |

### CHANNEL\_DESTROY

Sent by the client to signal the destruction of a voice channel. Be it
a channel being deleted, or all members in it leaving.

Same data as CHANNEL\_ASSIGN, but without `token`.

### VOICE\_STATE\_CREATE

Sent by the client to create a voice state.

| field | type | description |
| --: | :-- | :-- |
| user\_id | snowflake | user id |
| channel\_id | snowflake | channel id |
| guild\_id | Optional[snowflake] | guild id. not provided if dm / group dm |

### VOICE\_STATE\_DONE

Sent by the server to indicate the success of a VOICE\_STATE\_CREATE.

Has the same fields as VOICE\_STATE\_CREATE, but with extras:

| field | type | description |
| --: | :-- | :-- |
| session\_id | string | session id for the voice state |

### VOICE\_STATE\_DESTROY

Sent by the client when a user is leaving a channel OR moving between channels
in a guild. More on state transitions later on.

### VOICE\_STATE\_UPDATE

Sent to update an existing voice state. Potentially unused.

| field | type | description |
| --: | :-- | :-- |
| session\_id | string | session id for the voice state |

## Common logic scenarios

### User joins an unitialized voice channel

Since the channel is unitialized, both logic on initialization AND
user join is here.

 - Client will send a CHANNEL\_REQ.
 - Client MAY send a VOICE\_STATE\_CREATE right after as well.
 - The Server MUST process CHANNEL\_REQ first, so the Server can keep
    a lock on channel operations while it is initialized.
 - Reply with CHANNEL\_ASSIGN once initialization is done.
 - Process VOICE\_STATE\_CREATE

### Updating a voice channel

 - Client sends CHANNEL\_UPDATE.
 - Server DOES NOT reply.

### Destroying a voice channel

 - Client sends CHANNEL\_DESTROY.
 - Server MUST disconnect any users currently connected with its
    voice websocket.

### User joining an (initialized) voice channel

 - Client sends VOICE\_STATE\_CREATE
 - Server sends VOICE\_STATE\_DONE

### User leaves a channel

 - Client sends VOICE\_STATE\_DESTROY with the old fields

### User moves a channel

 - Client sends VOICE\_STATE\_DESTROY with the old fields
 - Client sends VOICE\_STATE\_CREATE with the new fields
 - Server sends VOICE\_STATE\_DONE

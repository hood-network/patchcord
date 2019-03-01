# Litecord Voice Server Protocol (LVSP)

LVSP is a protocol for Litecord to communicate with an external component
dedicated for voice data. The voice server is responsible for the
Voice Websocket Discord and Voice UDP connections.

LVSP runs over a websocket with TLS. The encoding is JSON.

## High level

In a high level:
 - Litecord connects to the Voice Server via a URL already configured
    beforehand.
 - 

## OP code table

"client" is litecord. "server" is the voice server.

**TODO:** voice state management.

| opcode | name | sent by |
| --: | :-- | :-- |
| 0 | HELLO | server |
| 1 | IDENTIFY | client |
| 2 | RESUME | client |
| 3 | READY | server |
| 4 | HEARTBEAT | client |
| 5 | HEARTBEAT\_ACK | server |

## high level overview

 - connect, receive HELLO
 - send IDENTIFY or RESUME
 - receive READY
 - start HEARTBEAT'ing

## HELLO message

Sent by the server when a connection is established.

| field | type | description |
| --: | :-- | :-- |
| heartbeat\_interval | integer | amount of milliseconds to heartbeat with |

## IDENTIFY message

Sent by the client to identify itself.

| field | type | description |
| --: | :-- | :-- |
| token | string | secret value kept between client and server |

## RESUME message

Sent by the client to resume itself from a failed websocket connection.

The server will resend its data, then send a READY message.

| field | type | description |
| --: | :-- | :-- |
| token | string | same value from IDENTIFY.token |
| seq | integer | last sequence number to resume from |

## READY message

**TODO**

| field | type | description |
| --: | :-- | :-- |

## HEARTBEAT message

Sent by the client as a keepalive / health monitoring method.

The server MUST reply with a HEARTBEAT\_ACK message back in a reasonable
time period.

**TODO**

| field | type | description |
| --: | :-- | :-- |

## HEARTBEAT\_ACK message

Sent by the server in reply to a HEARTBEAT message coming from the client.

**TODO**

| field | type | description |
| --: | :-- | :-- |

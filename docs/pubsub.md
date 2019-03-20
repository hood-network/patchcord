# Pub/Sub (Publish/Subscribe)

Please look over wikipedia or other sources to understand what it is.
This only documents how an events are generated and dispatched to clients.

## Event definition

Events are composed of two things:
 - Event type
 - Event payload

More information on how events are structured are in the Discord Gateway
API documentation.

## `StateManager` (litecord.gateway.state\_manager)

StateManager stores all available instances of `GatewayState` that identified.
Specific information is over the class' docstring, but we at least define
what it does here for the next class:

## `EventDispatcher` (litecord.dispatcher)

EventDispatcher declares the main interface between clients and the side-effects
(events) from topics they can subscribe to.

The topic / channel in EventDispatcher can be a User, or a Guild, or a Channel,
etc. Users subscribe to the channels they have access to manually, and get
unsubscribed when they e.g leave the guild the channel is on, etc.

Channels are identified by their backend and a given key uniquely identifying
the channel. The backend can be `guild`, `member`, `channel`, `user`,
`friend`, and `lazy_guild`. Backends *can* store the list of subscribers, but
that is not required.

Each backend has specific logic around dispatching a single event towards
all the subscribers of the given key. For example, the `guild` backend only
dispatches events to shards that are properly subscribed to the guild,
instead of all shards. The `user` backend just dispatches the event to
all available shards in `StateManager`, etc.

EventDispatcher also implements common logic, such as `dispatch_many` to
dispatch a single event to multpiple keys in a single backend. This is useful
e.g a user is updated and you want to dispatch `USER_UPDATE` events to many
guilds without having to write a loop yourself.

## Backend superclasses (litecord.pubsub.dispatcher)

The backend superclasses define what methods backends must provide to be
fully functional within EventDispatcher. They define e.g what is the type
of the keys, and have some specific backend helper methods, such as
`_dispatch_states` to dispatch an event to a list of states without
worrying about errors or writing the loop.

The other available superclass is `DispatchWithState` for backends that
require a list of subscribers to not repeat code. The only required method
to be implemented is `dispatch()` and you can see how that works out
on the backends that inherit from this class.

## Sending an event, practical

Call `app.dispatcher.dispatch(backend_string, key, event_type, event_payload)`.

example:
 - `dispatch('guild', guild_id, 'GUILD_UPDATE', guild)`, and other backends.
    The rules on how each backend dispatches its events can be found on the
    specific backend class.

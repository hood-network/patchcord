# Patchcord Admin API

Patchcord's Admin API uses the same authentication methods as Discord,
it's the same `Authorization` header, and the same token.

Only users who have the staff flag set can use the Admin API. Instance
owners can use the `./manage.py make_staff` manage task to set someone
as a staff user, granting them access over the administration functions.

The base path is `/api/v9/admin`.

## Information

### GET `/db`

Discover the database URL. This is useful for doing bulk operations on an admin frontend.

Returns:

| field | type | description |
| --: | :-- | :-- |
| url | string | the formatted dB URL

### GET `/counts`

Returns the counts of various tables in the database.

### GET `/snowflake`

Returns a generated snowflake for the current time.

Returns:

| field | type | description |
| --: | :-- | :-- |
| id | snowflake | the generated snowflake

## User management

### GET `/users`

Search users. Input is query arguments with the search parameters.

| field | type | description |
| --: | :-- | :-- |
| q | Optional[string] | username to query with optional discriminator; defaults to an empty string |
| limit | Optional[integer] | how many results to return; default 25, max 100 |
| offset | Optional[integer] | how many results to skip; used in pagination |

Returns:

| field | type | description |
| --: | :-- | :-- |
| users | List[User] | the users found
| total_results | integer | the total number of users found

### POST `/users`

Create a user. Returns a user object.

| field | type | description |
| --: | :-- | :-- |
| username | string | username |
| email | email | the email of the new user |
| password | string | password for the new user |
| id | Optional[snowflake] | the ID of the new user |
| date_of_birth | Optional[date] | the date of birth of the new user |

### GET `/users/<user_id>`

Returns a single user.

### PATCH `/users/<user_id>`

Update a single user's information. Takes the same fields as PATCH `/users/@me` with the addition of unconditional `flag` modifying.

Returns a user object on success.

**Note:** Changing a user's nitro badge is not defined via the flags.
Plus that would require adding an interface to user payments
through the Admin API.

[UserFlags]: https://discordapp.com/developers/docs/resources/user#user-object-user-flags

### DELETE `/users/<user_id>`

Delete a single user. Does not *actually* remove the user from the users row,
it changes the username to `Deleted User <random hex>`, etc.

Also disconnects all of the users' devices from the gateway.
Returns a user object.

### GET `/users/<user_id>/relationships`

Returns a single user's relationships.

### GET `/users/<user_id>/channels`

Returns a single user's private channels.

## Instance invites

Instance invites are used for instances that do not have open
registrations but want to let some people in regardless. Users
go to the `/invite_register.html` page in the instance and put
their data in.

### Instance Invite object

| field | type | description |
| --: | :-- | :-- |
| code | string | instance invite code |
| created\_at | ISO8907 timestamp | when the invite was created |
| max\_uses | integer | maximum amount of uses |
| uses | integer | how many times has the invite been used |

### GET `/instance-invites`

Get a list of instance invites.

### POST `/instance-invites`

Create an instance invite. Receives only the `max_uses`
field from the instance invites object. Returns a full
instance invite object.

### GET `/instance-invites/<invite>`

Get a single invite.

### DELETE `/instance-invites/<invite>`

Delete an invite. Does not have any input, only the instance invite's `code`
as the `<invite>` parameter in the URL.

Returns empty body 204 on success.

## Voice

### GET `/voice/regions/<region>`

Return a list of voice server objects for the region.

Returns empty list if the region does not exist.

| field | type | description |
| --: | :-- | :-- |
| hostname | string | the hostname of the voice server |
| last\_health | float | the health of the voice server |

### PUT `/voice/regions`

Create a voice region.

Receives JSON body as input, returns a list of voice region objects as output.

| field | type | description |
| --: | :-- | :-- |
| id | string | id of the voice region, "brazil", "us-east", "eu-west", etc |
| name | string | name of the voice region |
| vip | Optional[bool] | if voice region is vip-only, default false |
| deprecated | Optional[bool] | if voice region is deprecated, default false |
| custom | Optional[bool] | if voice region is custom-only, default false |

### PUT `/voice/regions/<region>/server`

Create a voice server for a region.

Returns empty body with 204 status code on success.

| field | type | description |
| --: | :-- | :-- |
| hostname | string | the hostname of the voice server |

### PUT `/voice/regions/<region>/deprecate`

Mark a voice region as deprecated. Disables any voice actions on guilds that are
using the voice region.

Returns empty body with 204 status code on success.

## Guilds

### GET `/guilds`

Search guilds. Input is query arguments with the search parameters.

| field | type | description |
| --: | :-- | :-- |
| q | Optional[string] | guild name to query with optional discriminator; defaults to an empty string |
| limit | Optional[integer] | how many results to return; default 25, max 100 |
| offset | Optional[integer] | how many results to skip; used in pagination |

Returns:

| field | type | description |
| --: | :-- | :-- |
| guilds | List[Guild] | the guilds found
| total_results | integer | the total number of guilds found

## POST `/guilds`

Create a guild. Returns a guild object.

Takes the same fields as the user equivalent with the addition of `features` and `id`.

### GET `/guilds/<guild_id>`

Get a full guild object.

### PATCH `/guilds/<guild_id>`

Update a single guild. Takes the same fields as the user equivalent with the addition of unconditionally modifying `features` and `unavailable`.

Returns a guild object on success.

### DELETE `/guilds/<guild_id>`

Delete a single guild. Returns 204 on success.

### PUT `/guilds/<guild_id>/features`

Replace the entire features list. Returns the new feature list following the same
structure as the input.

| field | type | description |
| --: | :-- | :-- |
| features | List[string] | new list of features |

### PATCH `/guilds/<guild_id>/features`

Insert features. Receives and returns the same structure as
PUT `/guilds/<guild_id>/features`.

### DELETE `/guilds/<guild_id>/features`

Remove features. Receives and returns the same structure as
PUT `/guilds/<guild_id>/features`.

## Channels

### GET `/channels/<channel_id>`

Get a single channel.

### PATCH `/channels/<channel_id>`

Update a single channel. Takes the same parameters as the user equivalent with the addition of the `recipients` field to unconditionally modify group channel recipients.

Returns a channel object on success.

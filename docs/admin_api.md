# Litecord Admin API

Litecord's Admin API uses the same authentication methods as Discord,
it's the same `Authorization` header, and the same token.

Only users who have the staff flag set can use the Admin API. Instance
owners can use the `./manage.py make_staff` manage task to set someone
as a staff user, granting them access over the administration functions.

The base path is `/api/v6/admin`.

## User management

### `PUT /users`

Create a user.
Returns a user object.

| field | type | description |
| --: | :-- | :-- |
| username | string | username |
| email | email | the email of the new user |
| password | str | password for the new user |

### `GET /users`

Search users. Input is query arguments with the search parameters.
Returns a list of user objects.

| field | type | description |
| --: | :-- | :-- |
| username | string | username |
| discriminator | string | discriminator |
| page | Optional[integer] | page, default 0 |
| per\_page | Optional[integer] | users per page, default 20, max 50 |

### `DELETE /users/<user_id>`

Delete a single user. Does not *actually* remove the user from the users row,
it changes the username to `Deleted User <random hex>`, etc.

Also disconnects all of the users' devices from the gateway.

Output:

| field | type | description |
| --: | :-- | :-- |
| old | user object | old user object pre-delete |
| new | user object | new user object post-delete |

### PATCH `/users/<user_id>`

Update a single user's information.

Returns a user object on success.

**Note:** You can not change any user's staff badge state (neither adding
it or removing it) to not cause privilege escalation/de-escalation (where
a staff makes more staff or a staff removes staff privileges of someone else).
Keep in mind the staff badge is what grants access to the Admin API, so.

**Note:** Changing a user's nitro badge is not defined via the flags.
Plus that would require adding an interface to user payments
through the Admin API.

[UserFlags]: https://discordapp.com/developers/docs/resources/user#user-object-user-flags

| field | type | description |
| --: | :-- | :-- |
| flags | [UserFlags] | user flags/badges |

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

### `GET /instance/invites`

Get a list of instance invites.

### `PUT /instance/invites`

Create an instance invite. Receives only the `max_uses`
field from the instance invites object. Returns a full
instance invite object.

### `DELETE /instance/invites/<invite>`

Delete an invite. Does not have any input, only the instance invite's `code`
as the `<invite>` parameter in the URL.

Returns empty body 204 on success, 404 on invite not found.

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

### GET `/guilds/<guild_id>`

Returns a partial guild object. Gives a 404 when the guild is not found.

### PATCH `/guilds/<guild_id>`

Update a single guild.
Dispatches `GUILD_UPDATE` to subscribers of the guild.

Returns a guild object or an unavailable guild object on success.

| field | type | description |
| --: | :-- | :-- |
| unavailable | bool | if the guild is unavailable |

### DELETE `/guilds/<guild_id>`

Delete a single guild. Returns 204 on success.

## Guild features

The currently supported features are:
 - `INVITE_SPLASH`, allows custom images to be put for invites.
 - `VIP_REGIONS`, allows a guild to use voice regions marked as VIP.
 - `VANITY_URL`, allows a custom invite URL to be used.
 - `MORE_EMOJI`, bumps the emoji limit from 50 to 200 (applies to static and
    animated emoji).
 - `VERIFIED`, adds a verified badge and a guild banner being shown on the
    top of the channel list.

Features that are not planned to be implemented:
 - `COMMERCE`
 - `NEWS`

### PATCH `/guilds/<guild_id>/features`

Patch the entire features list. Returns the new feature list following the same
structure as the input.

| field | type | description |
| --: | :-- | :-- |
| features | List[string] | new list of features |

### PUT `/guilds/<guild_id>/features`

Insert features. Receives and returns the same structure as
PATCH `/guilds/<guild_id>/features`.

### DELETE `/guilds/<guild_id>/features`

Remove features. Receives and returns the same structure as
PATCH `/guilds/<guild_id>/features`.

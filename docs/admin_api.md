# Litecord Admin API

the base path is `/api/v6/admin`.

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

Returns a partial guild object.

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

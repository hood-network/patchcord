# Litecord Admin API

the base path is `/api/v6/admin`.

## GET `/voice/regions/<region>`

Return a list of voice server objects for the region.

Returns empty list if the region does not exist.

| field | type | description |
| --: | :-- | :-- |
| hostname | string | the hostname of the voice server |
| last\_health | float | the health of the voice server |

## PUT `/voice/regions`

Create a voice region.

Receives JSON body as input, returns a list of voice region objects as output.

| field | type | description |
| --: | :-- | :-- |
| id | string | id of the voice region, "brazil", "us-east", "eu-west", etc |
| name | string | name of the voice region |
| vip | Optional[bool] | if voice region is vip-only, default false |
| deprecated | Optional[bool] | if voice region is deprecated, default false |
| custom | Optional[bool] | if voice region is custom-only, default false |

## PUT `/voice/regions/<region>/server`

Create a voice server for a region.

Returns empty body with 204 status code on success.

| field | type | description |
| --: | :-- | :-- |
| hostname | string | the hostname of the voice server |

## PUT `/voice/regions/<region>/deprecate`

Mark a voice region as deprecated. Disables any voice actions on guilds that are
using the voice region.

Returns empty body with 204 status code on success.

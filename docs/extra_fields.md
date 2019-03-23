# Extra / undocumented fields

Litecord provides extra fields for some objects due to the implicit requirement
on them by Discord clients. However, they're not documented.

Objects that aren't documented in the Discord API, such as relationships
aren't documented here. Take a look at the
[discord-unofficial-docs page][d-unofficial-docs] instead.

[d-unofficial-docs]: https://luna.gitlab.io/discord-unofficial-docs

## User object

| field | type | description |
| --: | :-- | :-- |
| premium | boolean | if the user has nitro |
| mobile | boolean? | if the user has a phone number registered |
| phone | string? | the user's phone number, hardcoded to `null` for litecord. |

## Author user object for messages from webhooks

It contains an extra `discriminator`, set to `'0000'`. This is Discord
undocumented behavior.

# API Differences

## Request Guild Members

### In regards to ID serialization

Request Guild Members does not follow the same logic Discord does when
invalid IDs are given on the `user_ids` field.

Instead of returning them as non-string numbers, **they're returned as-is.**

This should not cause any problems to well-formed requests.

### Assumptions on business logic

When using `user_ids`, Litecord will ignore the given `query` in the payload.

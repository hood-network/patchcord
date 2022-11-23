from typing import Dict
from dataclasses import fields as get_fields
import asyncpg

from litecord.models import PartialUser


class CacheManager:
    # User Id: Model
    users: Dict[int, PartialUser]

    async def load(self, db: asyncpg.Pool):
        fields = [field.name for field in get_fields(PartialUser)]
        raw_users = await db.fetchrow(
            f"""
            SELECT {','.join(fields)} FROM users;
            """,
        )
        self.users = {raw_user["id"]: PartialUser(**raw_user) for raw_user in raw_users}

    def cache_user(self, user: PartialUser):
        self.users[user.id] = user

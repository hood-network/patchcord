from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass, asdict, field

from litecord.enums import PremiumType


@dataclass
class PartialUser:
    id: int
    username: str
    discriminator: str
    avatar: Optional[str]
    avatar_decoration: Optional[str]
    flags: int
    bot: bool
    system: bool

    def to_json(self):
        json = asdict(self)
        json["id"] = str(self.id)
        json["public_flags"] = json.pop("flags")
        return json


@dataclass
class User(PartialUser):
    banner: Optional[str]
    bio: str
    accent_color: Optional[str]
    pronouns: str
    theme_colors: Optional[str]
    premium_since: Optional[datetime]
    premium_type: Optional[int]
    email: Optional[str]
    verified: bool
    mfa_enabled: bool
    date_of_birth: Optional[date]
    phone: Optional[str]

    def to_json(self, secure=True):
        json = super().to_json()
        json["flags"] = json["public_flags"]
        json["premium"] = json.pop("premium_since") is not None
        json["banner_color"] = hex(json["accent_color"]).replace("0x", "#") if json["accent_color"] else None

        # dob is never to be sent, its only used for nsfw_allowed
        dob = json.pop("date_of_birth")

        if secure:
            json["desktop"] = json["mobile"] = False
            json["phone"] = json["phone"] if json["phone"] else None

            today = date.today()

            json["nsfw_allowed"] = (
                ((today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))) >= 18) if dob else True
            )

        else:
            for field in ("email", "verified", "mfa_enabled", "phone", "premium_type"):
                json.pop(field)
        return json

    @property
    def nsfw_allowed(self):
        if not self.date_of_birth:
            return True
        today = date.today()

        return (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        ) >= 18

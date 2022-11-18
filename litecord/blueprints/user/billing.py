"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

import datetime
import json
from enum import Enum
from quart import Blueprint, jsonify
from typing import TYPE_CHECKING

from litecord.auth import token_check
from litecord.common.users import mass_user_update
from litecord.enums import UserFlags
from litecord.errors import BadRequest
from litecord.schemas import validate
from litecord.types import HOURS, timestamp_
from litecord.utils import snowflake_timestamp
from logbook import Logger

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)
bp = Blueprint("users_billing", __name__)


class PaymentSource(Enum):
    CREDIT = 1
    PAYPAL = 2


class SubscriptionStatus:
    ACTIVE = 1
    CANCELLED = 3


class SubscriptionType:
    # unknown
    PURCHASE = 1
    UPGRADE = 2


class SubscriptionPlan:
    CLASSIC = 1
    NITRO = 2


class PaymentGateway:
    STRIPE = 1
    BRAINTREE = 2


class PaymentStatus:
    SUCCESS = 1
    FAILED = 2


# how much should a payment be, depending
# of the subscription
AMOUNTS = {
    "premium_month_tier_0": 299,
    "premium_month_tier_1": 499,
    "premium_month_tier_2": 999,
    "premium_year_tier_1": 4999,
    "premium_year_tier_2": 9999,
}


CREATE_SUBSCRIPTION = {
    "payment_gateway_plan_id": {"type": "string"},
    "payment_source_id": {"coerce": int},
}


PAYMENT_SOURCE = {
    "billing_address": {
        "type": "dict",
        "schema": {
            "country": {"type": "string", "required": True},
            "city": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "line_1": {"type": "string", "required": False},
            "line_2": {"type": "string", "required": False},
            "postal_code": {"type": "string", "required": True},
            "state": {"type": "string", "required": True},
        },
    },
    "payment_gateway": {"type": "number", "required": True},
    "token": {"type": "string", "required": True},
}


async def get_payment_source_ids(user_id: int) -> list:
    rows = await app.db.fetch(
        """
    SELECT id
    FROM user_payment_sources
    WHERE user_id = $1
    """,
        user_id,
    )

    return [r["id"] for r in rows]


async def get_payment_ids(user_id: int) -> list:
    rows = await app.db.fetch(
        """
        SELECT id
        FROM user_payments
        WHERE user_id = $1
        """,
        user_id,
    )

    return [r["id"] for r in rows]


async def get_subscription_ids(user_id: int) -> list:
    rows = await app.db.fetch(
        """
    SELECT id
    FROM user_subscriptions
    WHERE user_id = $1
    """,
        user_id,
    )

    return [r["id"] for r in rows]


async def get_payment_source(user_id: int, source_id: int) -> dict:
    """Get a payment source's information."""
    source_type = await app.db.fetchval(
        """
        SELECT source_type
        FROM user_payment_sources
        WHERE id = $1 AND user_id = $2
        """,
        source_id,
        user_id,
    )

    source_type = PaymentSource(source_type)

    specific_fields = {
        PaymentSource.PAYPAL: ["paypal_email"],
        PaymentSource.CREDIT: ["expires_month", "expires_year", "brand", "cc_full"],
    }[source_type]

    fields = ",".join(specific_fields)

    extras_row = await app.db.fetchrow(
        f"""
    SELECT {fields}, billing_address, invalid, default_, id::text
    FROM user_payment_sources
    WHERE id = $1
    """,
        source_id,
    )

    derow = dict(extras_row)

    if source_type == PaymentSource.CREDIT:
        derow["last_4"] = derow["cc_full"][-4:]
        derow.pop("cc_full")

    derow["default"] = derow.pop("default_")
    derow["billing_address"] = (
        json.loads(derow["billing_address"])
        if isinstance(derow["billing_address"], str)
        else derow["billing_address"]
    )

    source = {
        "id": str(source_id),
        "type": source_type.value,
        "country": derow["billing_address"]["country"],
        "flags": 0,
        "payment_gateway": 1,
        "screen_status": 0,
    }

    return {**source, **derow}


TO_SUB_PLAN_ID = {
    "premium_month_tier_0": "978380692553465866",
    "premium_month_tier_1": "511651871736201216",
    "premium_month_tier_2": "511651880837840896",
    "premium_year_tier_1": "511651876987469824",
    "premium_year_tier_2": "511651885459963904",
}


async def get_subscription(subscription_id: int):
    """Get a subscription's information."""
    row = await app.db.fetchrow(
        """
        SELECT id::text, source_id::text AS payment_source_id,
            user_id,
            payment_gateway, payment_gateway_plan_id,
            period_start AS current_period_start,
            period_end AS current_period_end,
            canceled_at, s_type, status
        FROM user_subscriptions
        WHERE id = $1
        """,
        subscription_id,
    )

    drow = dict(row)

    drow["user_id"] = str(drow["user_id"])
    drow["type"] = drow["s_type"]
    drow.pop("s_type")

    to_tstamp = ["current_period_start", "current_period_end", "canceled_at"]

    for field in to_tstamp:
        drow[field] = timestamp_(drow[field])

    drow["created_at"] = snowflake_timestamp(int(drow["id"])).isoformat()

    drow["items"] = [
        {
            "id": "992118651056570430",
            "plan_id": TO_SUB_PLAN_ID[drow["payment_gateway_plan_id"]],
            "quantity": 1,
        }
    ]

    drow["renewal_mutations"] = {"items": []}

    return drow


async def get_payment(payment_id: int):
    """Get a single payment's information."""
    row = await app.db.fetchrow(
        """
        SELECT id::text, source_id, subscription_id, user_id,
            amount, amount_refunded, currency,
            description, status, tax, tax_inclusive
        FROM user_payments
        WHERE id = $1
        """,
        payment_id,
    )

    drow = dict(row)

    drow.pop("source_id")
    drow.pop("subscription_id")
    drow.pop("user_id")

    drow["created_at"] = app.winter_factory.to_datetime(int(drow["id"]))

    drow["payment_source"] = await get_payment_source(row["user_id"], row["source_id"])

    drow["subscription"] = await get_subscription(row["subscription_id"])

    return drow


async def create_payment(subscription_id):
    """Create a payment."""
    sub = await get_subscription(subscription_id)

    new_id = app.winter_factory.snowflake()

    amount = AMOUNTS[sub["payment_gateway_plan_id"]]

    await app.db.execute(
        """
        INSERT INTO user_payments (
            id, source_id, subscription_id, user_id,
            amount, amount_refunded, currency,
            description, status, tax, tax_inclusive
        )
        VALUES
            ($1, $2, $3, $4, $5, 0, $6, $7, $8, 0, false)
        """,
        new_id,
        int(sub["payment_source_id"]),
        subscription_id,
        int(sub["user_id"]),
        amount,
        "usd",
        "FUCK NITRO",
        PaymentStatus.SUCCESS,
    )

    return new_id


async def process_subscription(subscription_id: int):
    """Process a single subscription."""
    sub = await get_subscription(subscription_id)

    user_id = int(sub["user_id"])

    if sub["status"] != SubscriptionStatus.ACTIVE:
        log.debug("ignoring sub {}, not active", subscription_id)
        return

    # if the subscription is still active
    # (should get cancelled status on failed
    #  payments), then we should update premium status
    first_payment_id = await app.db.fetchval(
        """
        SELECT MIN(id)
        FROM user_payments
        WHERE subscription_id = $1
        """,
        subscription_id,
    )

    first_payment_ts = app.winter_factory.to_datetime(first_payment_id)

    premium_since = await app.db.fetchval(
        """
        SELECT premium_since
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    premium_since = premium_since or datetime.datetime.fromtimestamp(0)

    delta = abs(first_payment_ts - premium_since)

    # if the time difference between the first payment
    # and the premium_since column is more than 24h
    # we update it.
    if delta.total_seconds() < 24 * HOURS:
        return

    old_flags = await app.db.fetchval(
        """
        SELECT flags
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    new_flags = old_flags | UserFlags.premium_early
    log.debug("updating flags {}, {} => {}", user_id, old_flags, new_flags)

    await app.db.execute(
        """
        UPDATE users
        SET premium_since = $1, flags = $2
        WHERE id = $3
        """,
        first_payment_ts,
        new_flags,
        user_id,
    )

    # dispatch updated user to all possible clients
    await mass_user_update(user_id)


@bp.route("/@me/billing/payment-sources", methods=["GET"])
async def _get_billing_sources():
    user_id = await token_check()
    source_ids = await get_payment_source_ids(user_id)
    sources = [await get_payment_source(user_id, source_id) for source_id in source_ids]

    return jsonify(sources)


@bp.route("/@me/billing/subscriptions/preview", methods=["GET", "PATCH", "POST"])
@bp.route("/@me/billing/subscriptions", methods=["GET"])
async def _get_billing_subscriptions():
    user_id = await token_check()
    sub_ids = await get_subscription_ids(user_id)
    res = []

    for sub_id in sub_ids:
        res.append(await get_subscription(sub_id))

    return jsonify(res)


@bp.route("/@me/billing/payments", methods=["GET"])
async def _get_billing_payments():
    user_id = await token_check()
    payment_ids = await get_payment_ids(user_id)
    res = []

    for payment_id in payment_ids:
        res.append(await get_payment(payment_id))

    return jsonify(res)


@bp.route("/@me/billing/payment-sources", methods=["POST"])
async def _create_payment_source():
    user_id = await token_check()

    j = validate(await request.get_json(), PAYMENT_SOURCE)

    new_source_id = app.winter_factory.snowflake()

    await app.db.execute(
        """
        INSERT INTO user_payment_sources (id, user_id, source_type,
            default_, expires_month, expires_year, brand, cc_full,
            billing_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        new_source_id,
        user_id,
        PaymentSource.CREDIT.value,
        True,
        12,
        6969,
        "Visa",
        "4242424242424242",
        json.dumps(j["billing_address"]),
    )

    return jsonify(await get_payment_source(user_id, new_source_id))


@bp.route("/@me/billing/subscriptions", methods=["POST"])
async def _create_subscription():
    user_id = await token_check()
    j = validate(await request.get_json(), CREATE_SUBSCRIPTION)

    source = await get_payment_source(user_id, j["payment_source_id"])
    if not source:
        raise BadRequest(100002)

    plan_id = j["payment_gateway_plan_id"]
    if plan_id == "premium_year":
        plan_id = "premium_year_tier_1"
    elif plan_id == "premium_month":
        plan_id = "premium_month_tier_1"

    # tier 0 is new nitro basic
    # tier 1 is lightro / classic
    # tier 2 is nitro
    # no tier means old client that doesnt have tiers (so classic)

    period_end = {
        "premium_month_tier_0": "1 month",
        "premium_month_tier_1": "1 month",
        "premium_month_tier_2": "1 month",
        "premium_year_tier_1": "1 year",
        "premium_year_tier_2": "1 year",
    }[plan_id]

    new_id = app.winter_factory.snowflake()

    await app.db.execute(
        f"""
        INSERT INTO user_subscriptions (id, source_id, user_id,
            s_type, payment_gateway, payment_gateway_plan_id,
            status, period_end)
        VALUES ($1, $2, $3, $4, $5, $6, $7,
            now()::timestamp + interval '{period_end}')
        """,
        new_id,
        j["payment_source_id"],
        user_id,
        SubscriptionType.PURCHASE,
        PaymentGateway.STRIPE,
        plan_id,
        1,
    )

    await create_payment(new_id)

    # make sure we update the user's premium status
    # and dispatch respective user updates to other people.
    await process_subscription(new_id)

    return jsonify(await get_subscription(new_id))


@bp.route(
    "/@me/billing/invoices/preview",
    methods=["GET", "PATCH", "POST"],
    defaults={"subscription_id": None},
)
@bp.route(
    "/@me/billing/subscriptions/<int:subscription_id>/preview",
    methods=["GET", "PATCH", "POST"],
)
@bp.route("/@me/billing/subscriptions/<int:subscription_id>", methods=["GET"])
async def _get_subscription(subscription_id):
    await token_check()
    return jsonify(
        await get_subscription(
            subscription_id or int((await request.get_json())["subscription_id"])
        )
    )


@bp.route("/@me/billing/subscriptions/<int:subscription_id>", methods=["DELETE"])
async def _delete_subscription(subscription_id):
    user_id = await token_check()

    await app.db.execute(
        """
        DELETE FROM user_subscriptions
        WHERE id = $1 and user_id = $2
        """,
        subscription_id,
        user_id,
    )

    return "", 204


@bp.route("/@me/billing/subscriptions/<int:subscription_id>", methods=["PATCH"])
async def _patch_subscription(subscription_id):
    """change a subscription's payment source"""
    # user_id = await token_check()
    # j = validate(await request.get_json(), PATCH_SUBSCRIPTION)
    # returns subscription object
    pass


@bp.route("/@me/guilds/premium/subscription-slots")
async def _slots():
    return jsonify([])


@bp.route("/@me/billing/country-code", methods=["GET"])
@bp.route("/@me/billing/localized-pricing-promo", methods=["GET"])
async def _get_billing_country_code():
    return {"country_code": "US", "localized_pricing_promo": None}


@bp.route("/@me/billing/stripe/setup-intents", methods=["POST"])
async def _stripe_setup_intents():
    return {"client_secret": "gbawls"}


@bp.route("/@me/billing/payment-sources/validate-billing-address", methods=["POST"])
async def _validate_billing_address():
    return {"token": "gbawls"}

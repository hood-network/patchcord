import pprint
import json
from enum import Enum

from quart import Blueprint, jsonify, request, current_app as app

from litecord.auth import token_check
from litecord.schemas import validate
from litecord.blueprints.checks import guild_check
from litecord.storage import timestamp_
from litecord.snowflake import snowflake_datetime, get_snowflake

bp = Blueprint('users_billing', __name__)




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


CREATE_SUBSCRIPTION = {
    'payment_gateway_plan_id': {'type': 'string'},
    'payment_source_id': {'coerce': int}
}


PAYMENT_SOURCE = {
    'billing_address': {
        'type': 'dict',
        'schema': {
            'country': {'type': 'string', 'required': True},
            'city': {'type': 'string', 'required': True},
            'name': {'type': 'string', 'required': True},
            'line_1': {'type': 'string', 'required': False},
            'line_2': {'type': 'string', 'required': False},
            'postal_code': {'type': 'string', 'required': True},
            'state': {'type': 'string', 'required': True},
        }
    },
    'payment_gateway': {'type': 'number', 'required': True},
    'token': {'type': 'string', 'required': True},
}


async def get_payment_source_ids(user_id: int) -> list:
    rows = await app.db.fetch("""
    SELECT id
    FROM user_payment_sources
    WHERE user_id = $1
    """, user_id)

    return [r['id'] for r in rows]


async def get_payment_ids(user_id: int) -> list:
    rows = await app.db.fetch("""
    SELECT id
    FROM user_payments
    WHERE user_id = $1
    """, user_id)

    return [r['id'] for r in rows]


async def get_subscription_ids(user_id: int) -> list:
    rows = await app.db.fetch("""
    SELECT id
    FROM user_subscriptions
    WHERE user_id = $1
    """, user_id)

    return [r['id'] for r in rows]


async def get_payment_source(user_id: int, source_id: int) -> dict:
    """Get a payment source's information."""
    source = {}

    source_type = await app.db.fetchval("""
    SELECT source_type
    FROM user_payment_sources
    WHERE id = $1 AND user_id = $2
    """, source_id, user_id)

    source_type = PaymentSource(source_type)

    specific_fields = {
        PaymentSource.PAYPAL: ['paypal_email'],
        PaymentSource.CREDIT: ['expires_month', 'expires_year',
                               'brand', 'cc_full']
    }[source_type]

    fields = ','.join(specific_fields)

    extras_row = await app.db.fetchrow(f"""
    SELECT {fields}, billing_address, default_, id::text
    FROM user_payment_sources
    WHERE id = $1
    """, source_id)

    derow = dict(extras_row)

    if source_type == PaymentSource.CREDIT:
        derow['last_4'] = derow['cc_full'][-4:]
        derow.pop('cc_full')

    derow['default'] = derow['default_']
    derow.pop('default_')

    source = {
        'id': str(source_id),
        'type': source_type.value,
    }

    return {**source, **derow}


async def get_subscription(subscription_id: int):
    row = await app.db.execute("""
    SELECT id::text, source_id::text AS payment_source_id,
           payment_gateway, payment_gateway_plan_id,
           period_start AS current_period_start,
           period_end AS current_period_end,
           canceled_at, s_type, status
    FROM user_subscriptions
    WHERE id = $1
    """, subscription_id)

    drow = dict(row)

    drow['type'] = drow['s_type']
    drow.pop('s_type')

    to_tstamp = ['current_period_start', 'current_period_end', 'canceled_at']

    for field in to_tstamp:
        drow[field] = timestamp_(drow[field])

    return drow


async def get_payment(payment_id: int):
    row = await app.db.execute("""
    SELECT id::text, source_id, subscription_id,
           amount, amount_refunded, currency,
           description, status, tax, tax_inclusive
    FROM user_payments
    WHERE id = $1
    """, payment_id)

    drow = dict(row)
    drow['created_at'] = snowflake_datetime(int(drow['id']))
    return drow


@bp.route('/@me/billing/payment-sources', methods=['GET'])
async def _get_billing_sources():
    user_id = await token_check()
    source_ids = await get_payment_source_ids(user_id)

    res = []

    for source_id in source_ids:
        source = await get_payment_source(user_id, source_id)
        res.append(source)

    return jsonify(res)


@bp.route('/@me/billing/subscriptions', methods=['GET'])
async def _get_billing_subscriptions():
    user_id = await token_check()
    sub_ids = await get_subscription_ids(user_id)
    res = []

    for sub_id in sub_ids:
        res.append(await get_subscription(sub_id))

    return jsonify(res)


@bp.route('/@me/billing/payments', methods=['GET'])
async def _get_billing_payments():
    user_id = await token_check()
    payment_ids = await get_payment_ids(user_id)
    res = []

    for payment_id in payment_ids:
        res.append(await get_payment(payment_id))

    return jsonify(res)


@bp.route('/@me/billing/payment-sources', methods=['POST'])
async def _create_payment_source():
    user_id = await token_check()
    j = validate(await request.get_json(), PAYMENT_SOURCE)

    new_source_id = get_snowflake()

    await app.db.execute(
        """
        INSERT INTO user_payment_sources (id, user_id, source_type,
            default_, expires_month, expires_year, brand, cc_full,
            billing_address)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """, new_source_id, user_id, PaymentSource.CREDIT.value,
        True, 12, 6969, 'Visa', '4242424242424242',
        json.dumps(j['billing_address']))

    return jsonify(
        await get_payment_source(user_id, new_source_id)
    )


@bp.route('/@me/billing/subscriptions', methods=['POST'])
async def _create_subscription():
    user_id = await token_check()
    j = validate(await request.get_json(), CREATE_SUBSCRIPTION)


@bp.route('/@me/billing/subscriptions/<int:subscription_id>',
          methods=['DELETE'])
async def _delete_subscription(subscription_id):
    user_id = await token_check()
    return '', 204


@bp.route('/@me/billing/subscriptions/<int:subscription_id>',
          methods=['PATCH'])
async def _patch_subscription(subscription_id):
    """change a subscription's payment source"""
    user_id = await token_check()
    j = validate(await request.get_json(), PATCH_SUBSCRIPTION)
    # returns subscription object


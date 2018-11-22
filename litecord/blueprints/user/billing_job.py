"""
this file only serves the periodic payment job code.
"""
import datetime
from asyncio import sleep, CancelledError
from logbook import Logger

from litecord.blueprints.user.billing import (
    get_subscription, get_payment_ids, get_payment, create_payment,
    SubscriptionStatus
)

from litecord.snowflake import snowflake_datetime
from litecord.types import MINUTES, HOURS
from litecord.enums import UserFlags

from litecord.blueprints.users import mass_user_update

log = Logger(__name__)

# how many days until a payment needs
# to be issued
THRESHOLDS = {
    'premium_month_tier_1': 30,
    'premium_month_tier_2': 30,
    'premium_year_tier_1': 365,
    'premium_year_tier_2': 365,
}


async def _resched(app):
    log.debug('waiting 30 minutes for job.')
    await sleep(30 * MINUTES)
    app.sched.spawn(payment_job(app))


async def _process_user_payments(app, user_id: int):
    payments = await get_payment_ids(user_id, app.db)

    if not payments:
        log.debug('no payments for uid {}, skipping', user_id)
        return

    log.debug('{} payments for uid {}', len(payments), user_id)

    latest_payment = max(payments)

    payment_data = await get_payment(latest_payment, app.db)

    # calculate the difference between this payment
    # and now.
    now = datetime.datetime.now()
    payment_tstamp = snowflake_datetime(int(payment_data['id']))

    delta = now - payment_tstamp

    sub_id = int(payment_data['subscription']['id'])
    subscription = await get_subscription(
        sub_id, app.db)

    # if the max payment is X days old, we create another.
    # X is 30 for monthly subscriptions of nitro,
    # X is 365 for yearly subscriptions of nitro
    threshold = THRESHOLDS[subscription['payment_gateway_plan_id']]

    log.debug('delta {} delta days {} threshold {}',
              delta, delta.days, threshold)

    if delta.days > threshold:
        log.info('creating payment for sid={}',
                 sub_id)

        # create_payment does not call any Stripe
        # or BrainTree APIs at all, since we'll just
        # give it as free.
        await create_payment(sub_id, app)
    else:
        log.debug('sid={}, missing {} days',
                  sub_id, threshold - delta.days)


async def _process_subscription(app, subscription_id: int):
    sub = await get_subscription(subscription_id, app.db)

    user_id = int(sub['user_id'])

    if sub['status'] != SubscriptionStatus.ACTIVE:
        log.debug('ignoring sub {}, not active',
                  subscription_id)
        return

    # if the subscription is still active
    # (should get cancelled status on failed
    #  payments), then we should update premium status
    first_payment_id = await app.db.fetchval("""
    SELECT MIN(id)
    FROM user_payments
    WHERE subscription_id = $1
    """, subscription_id)

    first_payment_ts = snowflake_datetime(first_payment_id)

    premium_since = await app.db.fetchval("""
    SELECT premium_since
    FROM users
    WHERE id = $1
    """, user_id)

    premium_since = premium_since or datetime.datetime.fromtimestamp(0)

    delta = abs(first_payment_ts - premium_since)

    # if the time difference between the first payment
    # and the premium_since column is more than 24h
    # we update it.
    if delta.total_seconds() < 24 * HOURS:
        return

    old_flags = await app.db.fetchval("""
    SELECT flags
    FROM users
    WHERE id = $1
    """, user_id)

    new_flags = old_flags | UserFlags.premium_early
    log.debug('updating flags {}, {} => {}',
              user_id, old_flags, new_flags)

    await app.db.execute("""
    UPDATE users
    SET premium_since = $1, flags = $2
    WHERE id = $3
    """, first_payment_ts, new_flags, user_id)

    # dispatch updated user to all possible clients
    await mass_user_update(user_id, app)


async def payment_job(app):
    """Main payment job function.

    This function will check through users' payments
    and add a new one once a month / year.
    """
    log.debug('payment job start!')

    user_ids = await app.db.fetch("""
    SELECT DISTINCT user_id
    FROM user_payments
    """)

    log.debug('working {} users', len(user_ids))

    # go through each user's payments
    for row in user_ids:
        user_id = row['user_id']
        try:
            await _process_user_payments(app, user_id)
        except Exception:
            log.exception('error while processing user payments')

    subscribers = await app.db.fetch("""
    SELECT id
    FROM user_subscriptions
    """)

    for row in subscribers:
        try:
            await _process_subscription(app, row['id'])
        except Exception:
            log.exception('error while processing subscription')
    log.debug('rescheduling..')
    try:
        await _resched(app)
    except CancelledError:
        log.info('cancelled while waiting for resched')

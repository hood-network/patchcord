"""
this file only serves the periodic payment job code.
"""
import datetime
from asyncio import sleep
from logbook import Logger

from litecord.blueprints.user.billing import (
    get_subscription, get_payment_ids, get_payment, create_payment
)

from litecord.snowflake import snowflake_datetime

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
    log.debug('waiting 2 minutes for job.')
    await sleep(120)
    await app.sched.spawn(payment_job(app))


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

    await _resched(app)

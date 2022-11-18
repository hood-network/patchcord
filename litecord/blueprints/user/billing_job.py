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

"""
this file only serves the periodic payment job code.
"""
import datetime

from asyncio import sleep, CancelledError
from logbook import Logger
from typing import TYPE_CHECKING

from litecord.blueprints.user.billing import (
    get_subscription,
    get_payment_ids,
    get_payment,
    create_payment,
    process_subscription,
)

from litecord.types import MINUTES

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)

# how many days until a payment needs
# to be issued
THRESHOLDS = {
    "premium_month_tier_1": 30,
    "premium_month_tier_2": 30,
    "premium_year_tier_1": 365,
    "premium_year_tier_2": 365,
}


async def _resched():
    log.debug("waiting 30 minutes for job.")
    await sleep(30 * MINUTES)
    app.sched.spawn(payment_job())


async def _process_user_payments(user_id: int):
    payments = await get_payment_ids(user_id)

    if not payments:
        log.debug("no payments for uid {}, skipping", user_id)
        return

    log.debug("{} payments for uid {}", len(payments), user_id)

    latest_payment = max(payments)

    payment_data = await get_payment(latest_payment)

    # calculate the difference between this payment
    # and now.
    now = datetime.datetime.now()
    payment_tstamp = app.winter_factory.to_datetime(int(payment_data["id"]))

    delta = now - payment_tstamp

    sub_id = int(payment_data["subscription"]["id"])
    subscription = await get_subscription(sub_id)

    # if the max payment is X days old, we create another.
    # X is 30 for monthly subscriptions of nitro,
    # X is 365 for yearly subscriptions of nitro
    threshold = THRESHOLDS[subscription["payment_gateway_plan_id"]]

    log.debug("delta {} delta days {} threshold {}", delta, delta.days, threshold)

    if delta.days > threshold:
        log.info("creating payment for sid={}", sub_id)

        # create_payment does not call any Stripe
        # or BrainTree APIs at all, since we'll just
        # give it as free.
        await create_payment(sub_id)
    else:
        log.debug("sid={}, missing {} days", sub_id, threshold - delta.days)


async def payment_job():
    """Main payment job function.

    This function will check through users' payments
    and add a new one once a month / year.
    """
    log.debug("payment job start!")

    user_ids = await app.db.fetch(
        """
        SELECT DISTINCT user_id
        FROM user_payments
        """
    )

    log.debug("working {} users", len(user_ids))

    # go through each user's payments
    for row in user_ids:
        user_id = row["user_id"]
        try:
            await _process_user_payments(user_id)
        except Exception:
            log.exception("error while processing user payments")

    subscribers = await app.db.fetch(
        """
        SELECT id
        FROM user_subscriptions
        """
    )

    for row in subscribers:
        try:
            await process_subscription(row["id"])
        except Exception:
            log.exception("error while processing subscription")
    log.debug("rescheduling..")
    try:
        await _resched()
    except CancelledError:
        log.info("cancelled while waiting for resched")

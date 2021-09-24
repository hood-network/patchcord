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

from quart import Blueprint, jsonify

bp = Blueprint("store", __name__)

SKU_STUBS = {
    521842865731534868: [
        {
            "id": "511651856145973248",
            "name": "Nitro Monthly (Legacy)",
            "interval": 1,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521842865731534868",
            "currency": "usd",
            "price": 499,
            "price_tier": None,
        },
        {
            "id": "511651860671627264",
            "name": "Nitro Yearly (Legacy)",
            "interval": 2,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521842865731534868",
            "currency": "usd",
            "price": 4999,
            "price_tier": None,
        },
    ],
    521846918637420545: [
        {
            "id": "511651871736201216",
            "name": "Nitro Classic Monthly",
            "interval": 1,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521846918637420545",
            "currency": "usd",
            "price": 499,
            "price_tier": None,
        },
        {
            "id": "511651876987469824",
            "name": "Nitro Classic Yearly",
            "interval": 2,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521846918637420545",
            "currency": "usd",
            "price": 4999,
            "price_tier": None,
        },
    ],
    521847234246082599: [
        {
            "id": "511651880837840896",
            "name": "Nitro Monthly",
            "interval": 1,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521847234246082599",
            "currency": "usd",
            "price": 999,
            "price_tier": None,
        },
        {
            "id": "511651885459963904",
            "name": "Nitro Yearly",
            "interval": 2,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "521847234246082599",
            "currency": "usd",
            "price": 9999,
            "price_tier": None,
        },
        {
            "id": "642251038925127690",
            "name": "Nitro Quarterly",
            "interval": 1,
            "interval_count": 3,
            "tax_inclusive": True,
            "sku_id": "521847234246082599",
            "currency": "usd",
            "price": 2997,
            "price_tier": None,
        },
    ],
    590663762298667008: [
        {
            "id": "590665532894740483",
            "name": "Server Boost Monthly",
            "interval": 1,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "590663762298667008",
            "currency": "usd",
            "price": 499,
            "price_tier": None,
        },
        {
            "id": "590665538238152709",
            "name": "Server Boost Yearly",
            "interval": 2,
            "interval_count": 1,
            "tax_inclusive": True,
            "sku_id": "590663762298667008",
            "currency": "usd",
            "price": 4999,
            "price_tier": None,
        },
    ],
}


@bp.route("/published-listings/skus/<int:sku_id>/subscription-plans")
async def _stub_sku_plans(sku_id: int):
    stub_subscriptions = SKU_STUBS.get(sku_id)
    if stub_subscriptions is None:
        return "", 404
    return jsonify(stub_subscriptions)

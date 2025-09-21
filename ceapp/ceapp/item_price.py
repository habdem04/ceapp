# -*- coding: utf-8 -*-
import frappe
from frappe import _

def sync_pcs_price_from_kg_price(doc, method):
    """
    When an Item Price is created/updated with UOM = KG,
    automatically create/update the corresponding PCS price:
        rate_pcs = rate_kg × weight_per_unit (from Item)
    Only for items in Item Group 'Re-Bar'.
    Unidirectional: KG → PCS only.
    Uses `selling` field instead of `buying_or_selling`.
    """
    # Only process Selling prices
    if not doc.selling:
        return  # Skip if not a selling price

    # Get the linked Item
    try:
        item = frappe.get_doc("Item", doc.item_code)
    except frappe.DoesNotExistError:
        return

    # Only apply to Re-Bar items
    if not item or item.item_group != "Re-Bar":
        return

    # Ensure weight is set
    if not item.weight_per_unit or item.weight_per_unit <= 0:
        frappe.msgprint(_("Weight per Unit not set for {0}").format(item.name), alert=True)
        return

    # Normalize and check UOM (only trigger on KG/kgs)
    uom = (doc.uom or "").strip().lower()
    if uom not in ["kg", "kgs"]:
        return  # Do nothing if not KG

    # Get data
    price_list = doc.price_list
    currency = doc.currency or "ETB"
    rate_per_kg = doc.price_list_rate

    # Calculate derived PCS rate
    rate_per_pcs = rate_per_kg * item.weight_per_unit

    # Create or update PCS price
    _create_or_update_pcs_price(
        item=item,
        price_list=price_list,
        rate_per_pcs=rate_per_pcs,
        currency=currency
    )


def sync_rebar_prices_from_item(doc, method):
    """
    When Item is saved (e.g., weight updated),
    recalculate all PCS prices based on existing KG prices.
    """
    if doc.item_group != "Re-Bar":
        return

    if not doc.weight_per_unit or doc.weight_per_unit <= 0:
        return

    # Find all Selling prices with UOM = KG for this item
    kg_prices = frappe.get_all(
        "Item Price",
        filters={
            "item_code": doc.name,
            "selling": 1  # Only selling prices
        },
        fields=["name", "price_list", "price_list_rate", "currency", "uom"]
    )

    for price in kg_prices:
        uom = (price.uom or "").strip().lower()
        if uom not in ["kg", "kgs"]:
            continue  # Skip non-KG prices

        currency = price.currency or "ETB"
        rate_per_pcs = price.price_list_rate * doc.weight_per_unit

        _create_or_update_pcs_price(
            item=doc,
            price_list=price.price_list,
            rate_per_pcs=rate_per_pcs,
            currency=currency
        )


def _create_or_update_pcs_price(item, price_list, rate_per_pcs, currency="ETB"):
    """
    Helper: Create or update the PCS price for the given price list.
    """
    # Check if a PCS price already exists
    existing = frappe.get_all(
        "Item Price",
        filters={
            "item_code": item.name,
            "price_list": price_list,
            "uom": "PCS",
            "selling": 1  # Match only selling prices
        },
        limit=1
    )

    if existing:
        # Update existing PCS price
        frappe.db.set_value(
            "Item Price",
            existing[0].name,
            "price_list_rate",
            rate_per_pcs
        )
        frappe.msgprint(_(
            "✅ Updated PCS price for <b>{item}</b>: <b>{rate:,.2f} {curr}</b>"
        ).format(item=item.name, rate=rate_per_pcs, curr=currency), alert=True)
    else:
        # Create new PCS price
        new_price = frappe.get_doc({
            "doctype": "Item Price",
            "item_code": item.name,
            "item_name": item.item_name,
            "item_description": item.description,
            "price_list": price_list,
            "selling": 1,
            "buying": 0,
            "uom": "PCS",
            "price_list_rate": rate_per_pcs,
            "currency": currency
        })
        new_price.insert()
        frappe.msgprint(_(
            "🆕 Created PCS price for <b>{item}</b>: <b>{rate:,.2f} {curr}</b>"
        ).format(item=item.name, rate=rate_per_pcs, curr=currency), alert=True)
# -*- coding: utf-8 -*-
import frappe
from frappe import _

def update_weight_based_pricing(doc, method):
    """
    Universal server-side function for:
      - Quotation
      - Sales Order
    Calculates weight, applies active discount tier, recalculates rates, sets total discount.
    """
    # Skip if not Quotation or Sales Order
    if doc.doctype not in ["Quotation", "Sales Order"]:
        return

    total_net_weight = 0.0

    # === PHASE 1: Calculate Total Net Weight ===
    for item in doc.items:
        item_weight = frappe.db.get_value("Item", item.item_code, ["weight_per_unit", "weight_uom"], as_dict=1)
        if not item_weight or not item_weight.weight_per_unit:
            continue

        weight_per_unit = item_weight.weight_per_unit
        uom = (item_weight.weight_uom or "").strip()
        if not uom:
            continue

        uom_lower = uom.lower()
        weight_kg = 0.0

        if uom_lower in ["kg", "kgs"]:
            weight_kg = weight_per_unit
        elif uom_lower in ["metric ton", "tonne", "mt"]:
            weight_kg = weight_per_unit * 1000
        else:
            frappe.msgprint(_("Unsupported UOM for {0}: {1}").format(item.item_code, uom))
            continue

        total_net_weight += item.qty * weight_kg

    total_weight_mt = round(total_net_weight / 1000.0, 3)

    # Set parent fields
    if hasattr(doc, 'total_net_weight'):
        doc.total_net_weight = total_net_weight
    if hasattr(doc, 'total_weight_mt'):
        doc.total_weight_mt = total_weight_mt

    # === PHASE 2: Get Active Discount Tier ===
    discount_per_kg = 0.0

    tiers = frappe.get_all(
        "Weight-Based Discount Tier",
        fields=["from_metric_ton", "to_metric_ton", "discount_per_kg", "active"],
        filters={"active": 1},
        order_by="from_metric_ton"
    )

    for tier in tiers:
        if tier.from_metric_ton <= total_weight_mt <= tier.to_metric_ton:
            discount_per_kg = tier.discount_per_kg
            break

    if hasattr(doc, 'discount_per_kg'):
        doc.discount_per_kg = discount_per_kg

    # === PHASE 3: Update Each Item & Calculate Total Discount ===
    total_discount = 0.0

    for item in doc.items:
        item_weight = frappe.db.get_value("Item", item.item_code, ["weight_per_unit", "weight_uom"], as_dict=1)
        if not item_weight:
            continue

        weight_per_unit = item_weight.weight_per_unit
        uom = (item_weight.weight_uom or "").strip()
        if not uom:
            continue

        uom_lower = uom.lower()
        weight_per_unit_kg = 0.0

        if uom_lower in ["kg", "kgs"]:
            weight_per_unit_kg = weight_per_unit
        elif uom_lower in ["metric ton", "tonne", "mt"]:
            weight_per_unit_kg = weight_per_unit * 1000
        else:
            continue

        if weight_per_unit_kg == 0:
            continue

        # Get original rate (from price list or current rate)
        original_rate_per_pcs = item.get("price_list_rate") or item.get("rate") or 0
        if original_rate_per_pcs <= 0:
            original_rate_per_pcs = item.rate or 0

        original_amount = original_rate_per_pcs * item.qty

        try:
            original_rate_per_kg = round(original_rate_per_pcs / weight_per_unit_kg, 6)
        except ZeroDivisionError:
            original_rate_per_kg = 0.0

        new_rate_per_kg = max(0, original_rate_per_kg - discount_per_kg)
        new_rate_per_unit = round(new_rate_per_kg * weight_per_unit_kg, 6)
        new_amount = new_rate_per_unit * item.qty

        # Calculate discount for this item
        item_discount = original_amount - new_amount
        if item_discount > 0:
            total_discount += item_discount

        # === Update Child Fields ===
        if hasattr(item, 'original_rate_per_kg'):
            item.original_rate_per_kg = original_rate_per_kg
        if hasattr(item, 'new_rate_per_kg'):
            item.new_rate_per_kg = new_rate_per_kg

        item.rate = new_rate_per_unit
        item.amount = new_amount

        # Clear standard discount fields since we adjust rate
        item.discount_amount = 0
        item.discount_percentage = 0

    # === Set Total Discount ===
    if hasattr(doc, 'custom_total_discount'):
        doc.custom_total_discount = round(total_discount, 2)

    # Recalculate totals
    doc.calculate_taxes_and_totals()
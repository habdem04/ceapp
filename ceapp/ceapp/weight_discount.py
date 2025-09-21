# -*- coding: utf-8 -*-
import frappe
from frappe import _

@frappe.whitelist()
def get_weight_based_discount_tiers():
    """
    Return all Weight-Based Discount Tier rules.
    Called from client-side safely.
    """
    tiers = frappe.get_all(
        "Weight-Based Discount Tier",
        fields=["from_metric_ton", "to_metric_ton", "discount_per_kg"],
        order_by="from_metric_ton"
    )
    return tiers
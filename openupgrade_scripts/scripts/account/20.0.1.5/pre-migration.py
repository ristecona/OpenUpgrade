# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Odoo 20 moved the stock valuation settings and reports from stock_account to account.
# The inventory valuation report is a client action with the url path
# stock-valuation-closing: when it keeps its old external id, loading the data of
# account inserts a second action with the same path and stops on its unique constraint.
_renamed_xmlids = [
    (
        "stock_account.action_report_stock_valuation",
        "account.action_report_stock_valuation",
    ),
    (
        "stock_account.ir_cron_post_stock_valuation",
        "account.ir_cron_post_stock_valuation",
    ),
]

# Fields that stock_account defined and account defines now. Moving their external ids
# keeps the columns and the data and stops the module cleanup from dropping them when
# stock_account is updated before account.
_moved_fields = {
    "account.account": [
        "account_stock_expense_id",
        "account_stock_variation_id",
    ],
    "account.move.line": ["cogs_origin_id"],
    "product.category": [
        "account_stock_variation_id",
        "property_cost_method",
        "property_price_difference_account_id",
        "property_stock_journal",
        "property_stock_valuation_account_id",
        "property_valuation",
    ],
    "product.product": ["cost_method", "valuation"],
    "product.template": ["cost_method", "valuation"],
    "res.company": [
        "account_stock_journal_id",
        "account_stock_valuation_id",
        "cost_method",
        "inventory_period",
        "inventory_valuation",
    ],
}

# Stored selection values that 20.0 does not accept any more: a payment that is posted and
# not yet matched is 'paid' (Odoo recomputes paid and reconciled), the two types of
# reconciliation model are called matching_rule and reco_model.
_SELECTION_VALUES = """
    UPDATE account_payment SET state = 'paid' WHERE state = 'in_process';
    UPDATE account_reconcile_model SET rule_type = 'matching_rule'
     WHERE rule_type = 'invoice_matching';
    UPDATE account_reconcile_model SET rule_type = 'reco_model'
     WHERE rule_type = 'writeoff_button';
"""


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(env.cr, _SELECTION_VALUES)
    if openupgrade.is_module_installed(env.cr, "stock_account"):
        openupgrade.rename_xmlids(env.cr, _renamed_xmlids)
        for model, fields in _moved_fields.items():
            openupgrade.update_module_moved_fields(
                env.cr, model, fields, "stock_account", "account"
            )

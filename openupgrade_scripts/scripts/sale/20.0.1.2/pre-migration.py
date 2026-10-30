# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


def sale_delay_company_dependent(env):
    """product.template#sale_delay is company dependent in Odoo 20: a jsonb column that
    holds {"<company id>": days}. In 19.0 it was a plain integer column, and the ORM
    cannot cast an integer column to jsonb ("cannot cast type integer to jsonb"), so the
    upgrade stopped while loading the sale module.

    The old column is kept under its legacy name and the new one is filled with the
    same days for every company, as the field showed one value to everybody before.
    A value of 0 is the default of the field and is not stored.
    """
    openupgrade.rename_columns(env.cr, {"product_template": [("sale_delay", None)]})
    openupgrade.logged_query(
        env.cr, "ALTER TABLE product_template ADD COLUMN sale_delay jsonb"
    )
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE product_template t
           SET sale_delay = (
               SELECT jsonb_object_agg(c.id::text, t.openupgrade_legacy_20_0_sale_delay)
                 FROM res_company c)
         WHERE t.openupgrade_legacy_20_0_sale_delay IS NOT NULL
           AND t.openupgrade_legacy_20_0_sale_delay != 0
        """,
    )


def accrued_revenue_entry_is_a_server_action(env):
    """The accrued revenue entry of the list view is a server action in Odoo 20 and was
    a window action opening a wizard in 19.0, under the same external id. Loading the
    data then stops: "found record of different model ir.actions.act_window"."""
    openupgrade.delete_records_safely_by_xml_id(
        env, ["sale.action_accrued_revenue_entry_sale_order_line"]
    )


@openupgrade.migrate()
def migrate(env, version):
    sale_delay_company_dependent(env)
    accrued_revenue_entry_is_a_server_action(env)

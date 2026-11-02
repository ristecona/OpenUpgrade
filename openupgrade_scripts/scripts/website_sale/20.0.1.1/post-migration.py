# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# 20.0 splits the checkout into more steps (an address step at /shop/address and a
# payment confirmation step at /shop/payment/transaction) and reads the steps of the
# current website. Odoo only creates the per-website copies of the generic steps when
# website_sale is installed (post_init_hook), so a database that comes from 19.0 has the
# generic records for the new steps but no copy for any website, and the address step
# fails with "Expected singleton: website.checkout.step()".


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(
        env.cr,
        """
        INSERT INTO website_checkout_step (
            name, sequence, step_href, main_button_label, back_button_label,
            website_id, show_in_breadcrumb, is_published,
            create_uid, write_uid, create_date, write_date)
        SELECT g.name, g.sequence, g.step_href, g.main_button_label,
               g.back_button_label, w.id, g.show_in_breadcrumb, TRUE,
               %(uid)s, %(uid)s, NOW() AT TIME ZONE 'UTC', NOW() AT TIME ZONE 'UTC'
          FROM website_checkout_step g
         CROSS JOIN website w
         WHERE g.website_id IS NULL
           AND NOT EXISTS (
               SELECT 1 FROM website_checkout_step s
                WHERE s.website_id = w.id AND s.step_href = g.step_href)
        """,
        {"uid": 1},
    )

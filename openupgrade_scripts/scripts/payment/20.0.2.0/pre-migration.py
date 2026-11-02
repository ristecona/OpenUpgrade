# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Odoo 20 has one generic redirect form and the provider field redirect_form_view_id is
# gone. The old per-provider views (payment_mollie.redirect_form,
# payment_custom.redirect_form, ...) are obsolete and are deleted at the end of the
# update, which the foreign key of the left-over column would block.


@openupgrade.migrate()
def migrate(env, version):
    if openupgrade.column_exists(env.cr, "payment_provider", "redirect_form_view_id"):
        openupgrade.logged_query(
            env.cr, "UPDATE payment_provider SET redirect_form_view_id = NULL"
        )

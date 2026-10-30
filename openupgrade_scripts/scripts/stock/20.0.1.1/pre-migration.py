# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Odoo 20 names the unit of measure of a line `uom_id` on every model; before it was
# `product_uom_id` or `product_uom`, depending on the model. The column and the field
# are renamed, so the data stays and the new required column has its values.
_renamed_fields = [
    (
        "stock.move",
        "stock_move",
        "product_uom",
        "uom_id",
    ),
    (
        "stock.move.line",
        "stock_move_line",
        "product_uom_id",
        "uom_id",
    ),
]


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _renamed_fields)

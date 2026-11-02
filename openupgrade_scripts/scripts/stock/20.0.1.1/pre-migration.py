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


# Odoo 20 keeps only 'lot' and 'serial' as the tracking method of a template: a product
# that is tracked by quantity only, or not at all, has no tracking method (the new field
# store_by tells the two apart through is_storable). The 'none' of 19.0 is not a valid
# value any more, and the computation of store_by hands it on, so opening a product
# fails with: Wrong value for product.template.store_by: 'none'.
_NO_TRACKING = "UPDATE product_template SET tracking = NULL WHERE tracking = 'none'"

# The label formats of an operation type are named after the layout in 20.0.
_LABEL_FORMAT = (
    "UPDATE stock_picking_type SET product_label_format = 'barcode_2x7_price' "
    "WHERE product_label_format = '2x7xprice'"
)


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.rename_fields(env, _renamed_fields)
    openupgrade.logged_query(env.cr, _NO_TRACKING)
    openupgrade.logged_query(env.cr, _LABEL_FORMAT)

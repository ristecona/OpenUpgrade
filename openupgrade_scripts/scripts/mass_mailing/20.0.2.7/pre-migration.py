# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade


@openupgrade.migrate()
def migrate(env, version):
    """The merge action of the mailing lists is a server action in Odoo 20 and was a
    window action opening a wizard in 19.0, under the same external id. Loading the
    data then stops: "found record of different model ir.actions.act_window"."""
    openupgrade.delete_records_safely_by_xml_id(
        env, ["mass_mailing.mailing_list_merge_action"]
    )

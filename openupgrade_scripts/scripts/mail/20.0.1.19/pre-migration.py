# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Chat channels (channel_type = 'chat') are the direct messages and small groups of
# Discuss. Odoo 20 gives every chat a stored member_indices ("p11,p107725": its partners
# and guests, sorted) with a unique index, so there is at most one chat per combination
# of members, and a check that a chat has members. Earlier versions did not enforce
# that: a database can hold several chats between the same people, created by two users
# opening the conversation at the same time or by a client that created one per click.
# The unique index then fails when the module loads and the whole upgrade stops.

# Messages, attachments and followers of a chat point to it by model and id, without a
# foreign key. The rest of what hangs on a channel (members, pinned messages, call
# history) is removed by its on delete cascade.
_DUPLICATE_CHATS = """
    WITH chats AS (
        SELECT c.id,
               string_agg(
                   CASE WHEN m.partner_id IS NOT NULL THEN 'p' || m.partner_id
                        ELSE 'g' || m.guest_id END,
                   ',' ORDER BY m.partner_id, m.guest_id) AS members
          FROM discuss_channel c
          JOIN discuss_channel_member m ON m.channel_id = c.id
         WHERE c.channel_type = 'chat'
         GROUP BY c.id
    )
    SELECT id, min(id) OVER (PARTITION BY members) AS keep_id
      FROM chats
"""


def merge_duplicate_chats(env):
    """Keep the oldest chat of each combination of members and move the history of
    the others into it."""
    env.cr.execute(
        f"SELECT id, keep_id FROM ({_DUPLICATE_CHATS}) d WHERE id != keep_id"  # noqa: S608
    )
    duplicates = env.cr.fetchall()
    if not duplicates:
        return
    openupgrade.logged_query(
        env.cr,
        "CREATE TEMPORARY TABLE openupgrade_duplicate_chat (id int, keep_id int)",
    )
    env.cr.executemany(
        "INSERT INTO openupgrade_duplicate_chat (id, keep_id) VALUES (%s, %s)",
        duplicates,
    )
    for table in ("mail_message", "ir_attachment"):
        model_column = "model" if table == "mail_message" else "res_model"
        id_column = "res_id"
        openupgrade.logged_query(
            env.cr,
            f"""
            UPDATE {table} t
               SET {id_column} = d.keep_id
              FROM openupgrade_duplicate_chat d
             WHERE t.{model_column} = 'discuss.channel' AND t.{id_column} = d.id
            """,  # noqa: S608
        )
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM mail_followers f
         USING openupgrade_duplicate_chat d
         WHERE f.res_model = 'discuss.channel' AND f.res_id = d.id
        """,
    )
    openupgrade.logged_query(
        env.cr,
        """
        DELETE FROM discuss_channel c
         USING openupgrade_duplicate_chat d
         WHERE c.id = d.id
        """,
    )
    openupgrade.message(
        env.cr,
        "mail",
        "discuss_channel",
        "channel_type",
        "%s duplicate chat channel(s) were merged into the oldest chat with the same "
        "members, because Odoo 20 allows one chat per combination of members.",
        len(duplicates),
    )
    openupgrade.logged_query(env.cr, "DROP TABLE openupgrade_duplicate_chat")


def chats_without_members_become_groups(env):
    """A chat must have members in Odoo 20. A group has no member indices, so a chat
    that lost all its members and keeps its history becomes a group."""
    openupgrade.logged_query(
        env.cr,
        """
        UPDATE discuss_channel c
           SET channel_type = 'group'
         WHERE c.channel_type = 'chat'
           AND NOT EXISTS (SELECT 1 FROM discuss_channel_member m WHERE m.channel_id = c.id)
        """,
    )


def link_admin_member_of_administrators_channel(env):
    """Odoo 20 declares the membership of the administrator in the Administrators
    channel as a record with an external id. A database upgraded from 19.0 already has
    that membership, created by the code that made the channel, without the id, and
    loading the data file tries to create it a second time against the unique index
    on (channel, partner). Give the existing membership the id."""
    xmlid = "channel_member_channel_admin_partner_admin"
    env.cr.execute("""
        SELECT m.id
          FROM discuss_channel_member m
          JOIN ir_model_data channel ON channel.model = 'discuss.channel'
               AND channel.res_id = m.channel_id
               AND channel.module = 'mail' AND channel.name = 'channel_admin'
          JOIN ir_model_data partner ON partner.model = 'res.partner'
               AND partner.res_id = m.partner_id
               AND partner.module = 'base' AND partner.name = 'partner_admin'
         ORDER BY m.id
         LIMIT 1
        """)
    row = env.cr.fetchone()
    if row:
        openupgrade.add_xmlid(env.cr, "mail", xmlid, "discuss.channel.member", row[0])


@openupgrade.migrate()
def migrate(env, version):
    chats_without_members_become_groups(env)
    merge_duplicate_chats(env)
    link_admin_member_of_administrators_channel(env)

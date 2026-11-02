# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Odoo 20 changes how the images of a product are tied to its variants.
#
# 19.0: an extra image (product.image) belongs to a variant through product_variant_id.
# 20.0: it lists the attribute values it is for (attribute_value_ids, with the stored
# has_attribute_value), and a variant shows the images whose values it has, stored in
# the relation product_product_image_rel (variant_image_ids). The variant's own main
# image (image_variant_1920) stays, and an extra image copy of it is what puts it in the
# gallery.
#
# Odoo converts the old data with product.template#_create_extra_variant_images, called
# from data/data.xml on every update of website_sale. It reads the content of every
# variant image into memory and creates one record per image: with 626,715 variant
# images and 71,090 template images (Maximum Image) the hop dies with a MemoryError
# after nine minutes of computing has_attribute_value through the ORM. This does the
# same in SQL, comparing the checksums Odoo stores for every file instead of the
# content, and creating the new images with attachment rows that point to the same
# stored files. The function is replaced by a no-op for this run.


def _skip_odoo_conversion():
    # website_sale is not in the registry yet, but its module is importable: patching the
    # class here is seen when data.xml calls the function later in the same process.
    from odoo import api
    from odoo.addons.website_sale.models import product_template

    # data.xml calls it with no record ids, which only works for a model method, so the
    # replacement has to carry the @api.model marker too.
    @api.model
    def _create_extra_variant_images(self):
        return None

    product_template.ProductTemplate._create_extra_variant_images = (
        _create_extra_variant_images
    )


_ATTACHMENT_COLUMNS = """
    SELECT string_agg(quote_ident(column_name), ', ' ORDER BY ordinal_position)
      FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'ir_attachment'
       AND column_name NOT IN ('id', 'res_model', 'res_field', 'res_id', 'name')
"""


def _copy_attachments(env, table, field, new_field, source_field):
    """New attachment rows for the new images, same stored file as the source attachment
    of the variant (or template) the image is made from."""
    env.cr.execute(_ATTACHMENT_COLUMNS)
    columns = env.cr.fetchone()[0]
    select = ", ".join("a." + c.strip() for c in columns.split(","))
    openupgrade.logged_query(
        env.cr,
        f"""
        INSERT INTO ir_attachment (name, res_model, res_field, res_id, {columns})
        SELECT '{new_field}', 'product.image', '{new_field}', n.nid, {select}
          FROM {table} n
          JOIN ir_attachment a ON a.res_model = n.src_model AND a.res_field = '{source_field}'
                              AND a.res_id = n.src_id
        """,  # noqa: S608
    )


def convert_variant_images(env):
    cr = env.cr
    _skip_odoo_conversion()
    openupgrade.logged_query(
        cr,
        "ALTER TABLE product_image ADD COLUMN IF NOT EXISTS has_attribute_value boolean",
    )
    openupgrade.logged_query(
        cr,
        """
        CREATE TABLE IF NOT EXISTS product_image_attribute_value_rel (
            product_image_id integer NOT NULL REFERENCES product_image (id) ON DELETE CASCADE,
            product_template_attribute_value_id integer NOT NULL
                REFERENCES product_template_attribute_value (id) ON DELETE CASCADE,
            PRIMARY KEY (product_image_id, product_template_attribute_value_id));
        CREATE TABLE IF NOT EXISTS product_product_image_rel (
            product_product_id integer NOT NULL REFERENCES product_product (id) ON DELETE CASCADE,
            product_image_id integer NOT NULL REFERENCES product_image (id) ON DELETE CASCADE,
            PRIMARY KEY (product_product_id, product_image_id));
        CREATE INDEX IF NOT EXISTS product_image_attribute_value_rel_value_idx
            ON product_image_attribute_value_rel (product_template_attribute_value_id);
        CREATE INDEX IF NOT EXISTS product_product_image_rel_image_idx
            ON product_product_image_rel (product_image_id);
        """,
    )
    # 1. Extra images of a variant are for that variant's attribute values.
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_image_attribute_value_rel
        SELECT i.id, c.product_template_attribute_value_id
          FROM product_image i
          JOIN product_variant_combination c ON c.product_product_id = i.product_variant_id
          JOIN product_template_attribute_value v
            ON v.id = c.product_template_attribute_value_id AND v.product_tmpl_id = i.product_tmpl_id
        ON CONFLICT DO NOTHING
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_product_image_rel
        SELECT DISTINCT i.product_variant_id, i.id
          FROM product_image i
          JOIN product_product p ON p.id = i.product_variant_id AND p.product_tmpl_id = i.product_tmpl_id
         WHERE EXISTS (SELECT 1 FROM product_image_attribute_value_rel r WHERE r.product_image_id = i.id)
        ON CONFLICT DO NOTHING
        """,
    )
    # 2. What the conversion of Odoo compares: the first extra image of a template, and of
    #    a variant, by sequence. Before anything is added.
    openupgrade.logged_query(
        cr,
        """
        CREATE TEMPORARY TABLE ou_first_template_extra AS
        SELECT DISTINCT ON (i.product_tmpl_id) i.product_tmpl_id AS tmpl_id, i.sequence, a.checksum
          FROM product_image i
          LEFT JOIN ir_attachment a ON a.res_model = 'product.image' AND a.res_field = 'image_1920'
                                   AND a.res_id = i.id
         ORDER BY i.product_tmpl_id, i.sequence, i.id;
        CREATE TEMPORARY TABLE ou_first_variant_extra AS
        SELECT DISTINCT ON (r.product_product_id) r.product_product_id AS variant_id, i.sequence, a.checksum
          FROM product_product_image_rel r
          JOIN product_image i ON i.id = r.product_image_id
          LEFT JOIN ir_attachment a ON a.res_model = 'product.image' AND a.res_field = 'image_1920'
                                   AND a.res_id = i.id
         ORDER BY r.product_product_id, i.sequence, i.id;
        """,
    )
    # 3. The main image of a template that is not the first extra image becomes one, put
    #    first. Ids are taken before those of the variant images, which sort after it.
    openupgrade.logged_query(
        cr,
        """
        CREATE TEMPORARY TABLE ou_new_template_image AS
        SELECT nextval('product_image_id_seq') AS nid, t.id AS tmpl_id, 'product.template' AS src_model,
               t.id AS src_id, coalesce(f.sequence, 0) - 1 AS seq
          FROM product_template t
          JOIN ir_attachment m ON m.res_model = 'product.template' AND m.res_field = 'image_1920'
                              AND m.res_id = t.id
          LEFT JOIN ou_first_template_extra f ON f.tmpl_id = t.id
         WHERE t.active AND f.checksum IS DISTINCT FROM m.checksum
        """,
    )
    # 4. The main image of a variant that is not its first extra image becomes one.
    openupgrade.logged_query(
        cr,
        """
        CREATE TEMPORARY TABLE ou_new_variant_image AS
        SELECT nextval('product_image_id_seq') AS nid, p.id AS variant_id, p.product_tmpl_id AS tmpl_id,
               'product.product' AS src_model, p.id AS src_id, coalesce(f.sequence, 0) - 1 AS seq
          FROM product_product p
          JOIN product_template t ON t.id = p.product_tmpl_id AND t.active
          JOIN ir_attachment tm ON tm.res_model = 'product.template' AND tm.res_field = 'image_1920'
                               AND tm.res_id = t.id
          JOIN ir_attachment a ON a.res_model = 'product.product' AND a.res_field = 'image_variant_1920'
                              AND a.res_id = p.id
          LEFT JOIN ou_first_variant_extra f ON f.variant_id = p.id
         WHERE p.active AND f.checksum IS DISTINCT FROM a.checksum
        """,
    )
    # 5. The records. The name is what the display name of the template or variant is.
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_image (id, name, sequence, product_tmpl_id, can_image_1024_be_zoomed,
                                   create_uid, create_date, write_uid, write_date)
        SELECT n.nid, coalesce(t.name->>'en_US', (SELECT min(v.value) FROM jsonb_each_text(t.name) v)),
               n.seq, n.tmpl_id, coalesce(t.can_image_1024_be_zoomed, false), 1, now() AT TIME ZONE 'utc',
               1, now() AT TIME ZONE 'utc'
          FROM ou_new_template_image n JOIN product_template t ON t.id = n.tmpl_id
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_image (id, name, sequence, product_tmpl_id, can_image_1024_be_zoomed,
                                   create_uid, create_date, write_uid, write_date)
        SELECT n.nid,
               coalesce('[' || p.default_code || '] ', '')
                 || coalesce(t.name->>'en_US', (SELECT min(v.value) FROM jsonb_each_text(t.name) v))
                 || coalesce((SELECT ' (' || string_agg(coalesce(av.name->>'en_US', ''), ', '
                                                         ORDER BY l.sequence, v.id) || ')'
                                FROM product_variant_combination c
                                JOIN product_template_attribute_value v
                                  ON v.id = c.product_template_attribute_value_id
                                JOIN product_template_attribute_line l ON l.id = v.attribute_line_id
                                JOIN product_attribute_value av ON av.id = v.product_attribute_value_id
                               WHERE c.product_product_id = p.id AND l.active
                                 AND (SELECT count(*) FROM product_template_attribute_line x
                                       WHERE x.product_tmpl_id = t.id AND x.active) > 0), ''),
               n.seq, n.tmpl_id, coalesce(p.can_image_variant_1024_be_zoomed, false), 1,
               now() AT TIME ZONE 'utc', 1, now() AT TIME ZONE 'utc'
          FROM ou_new_variant_image n
          JOIN product_product p ON p.id = n.variant_id
          JOIN product_template t ON t.id = n.tmpl_id
        """,
    )
    # 6. The files: attachment rows for the new images that share the stored file.
    for new_table, source_1024 in (
        ("ou_new_template_image", "image_1024"),
        ("ou_new_variant_image", "image_variant_1024"),
    ):
        _copy_attachments(
            env,
            new_table,
            "image_1920",
            "image_1920",
            (
                "image_1920"
                if new_table == "ou_new_template_image"
                else "image_variant_1920"
            ),
        )
        _copy_attachments(env, new_table, "image_1024", "image_1024", source_1024)
    # 7. Attribute values: a variant image is for the values of its variant, the template
    #    image for the values of the variants that have no image of their own, when the
    #    template has several variants.
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_image_attribute_value_rel
        SELECT n.nid, c.product_template_attribute_value_id
          FROM ou_new_variant_image n
          JOIN product_variant_combination c ON c.product_product_id = n.variant_id
          JOIN product_template_attribute_value v
            ON v.id = c.product_template_attribute_value_id AND v.product_tmpl_id = n.tmpl_id
        ON CONFLICT DO NOTHING;
        INSERT INTO product_image_attribute_value_rel
        SELECT n.nid, c.product_template_attribute_value_id
          FROM ou_new_template_image n
          JOIN product_product p ON p.product_tmpl_id = n.tmpl_id AND p.active
          JOIN product_variant_combination c ON c.product_product_id = p.id
         WHERE (SELECT count(*) FROM product_product x WHERE x.product_tmpl_id = n.tmpl_id AND x.active) > 1
           AND NOT EXISTS (SELECT 1 FROM ir_attachment o WHERE o.res_model = 'product.product'
                              AND o.res_field = 'image_variant_1920' AND o.res_id = p.id)
        ON CONFLICT DO NOTHING;
        """,
    )
    # The tables above are new in this transaction, so autovacuum has not analysed them
    # and the planner would guess their size; with millions of rows that picks plans
    # that never finish.
    openupgrade.logged_query(
        cr,
        """
        CREATE INDEX ON ou_new_variant_image (nid);
        CREATE INDEX ON ou_new_template_image (nid);
        ANALYZE ou_new_variant_image;
        ANALYZE ou_new_template_image;
        ANALYZE product_image_attribute_value_rel;
        """,
    )
    openupgrade.logged_query(
        cr,
        """
        UPDATE product_image i SET has_attribute_value = EXISTS (
            SELECT 1 FROM product_image_attribute_value_rel r WHERE r.product_image_id = i.id)
        """,
    )
    # 8. variant_image_ids: the images whose values the variant has, line by line.
    openupgrade.logged_query(
        cr,
        """
        INSERT INTO product_product_image_rel
        SELECT n.variant_id, n.nid FROM ou_new_variant_image n
         WHERE EXISTS (SELECT 1 FROM product_image_attribute_value_rel r WHERE r.product_image_id = n.nid)
        ON CONFLICT DO NOTHING;
        INSERT INTO product_product_image_rel
        SELECT p.id, n.nid
          FROM ou_new_template_image n
          JOIN product_product p ON p.product_tmpl_id = n.tmpl_id AND p.active
         WHERE EXISTS (SELECT 1 FROM product_image_attribute_value_rel r WHERE r.product_image_id = n.nid)
           AND NOT EXISTS (
               SELECT 1
                 FROM (SELECT DISTINCT v.attribute_line_id
                         FROM product_image_attribute_value_rel r
                         JOIN product_template_attribute_value v
                           ON v.id = r.product_template_attribute_value_id
                        WHERE r.product_image_id = n.nid) l
                WHERE NOT EXISTS (
                    SELECT 1 FROM product_variant_combination c
                      JOIN product_template_attribute_value pv
                        ON pv.id = c.product_template_attribute_value_id
                     WHERE c.product_product_id = p.id AND pv.attribute_line_id = l.attribute_line_id
                       AND pv.id IN (SELECT r2.product_template_attribute_value_id
                                       FROM product_image_attribute_value_rel r2
                                      WHERE r2.product_image_id = n.nid)))
        ON CONFLICT DO NOTHING;
        """,
    )
    cr.execute(
        "SELECT (SELECT count(*) FROM ou_new_template_image), (SELECT count(*) FROM ou_new_variant_image)"
    )
    templates, variants = cr.fetchone()
    openupgrade.message(
        cr,
        "website_sale",
        "product_image",
        "has_attribute_value",
        "Odoo's conversion of variant images was replaced by SQL: %s template main images "
        "and %s variant main images became extra images, attribute values were set on "
        "the extra images of variants.",
        templates,
        variants,
    )


@openupgrade.migrate()
def migrate(env, version):
    convert_variant_images(env)

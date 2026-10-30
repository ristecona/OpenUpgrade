# Copyright 2026 Riste Kabranov
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from openupgradelib import openupgrade

# Up to 19.0 a payment method (payment.method) is shared by the providers that list it
# in payment_method_ids. In 20.0 every method belongs to one provider (provider_id,
# required, unique with the code) and transactions and tokens point at the method of
# their own provider. The methods that the provider modules create while loading are
# already per provider; this gives every provider that has transactions or tokens on an
# old method a method of its own with the same code and moves the references over.
# Without it the old rows keep a null provider_id and the not null constraint on the
# column is not added.

_CONVERT_PAYMENT_METHODS = """
-- 1. Every provider that has a transaction or token on an old, provider-less method gets
--    a method of its own with the same code, unless it already has one.
INSERT INTO payment_method (
    name, sequence, create_uid, create_date, write_uid, write_date,
    primary_payment_method_id, code, support_refund, active, support_tokenization,
    support_express_checkout, support_manual_capture, provider_id, allow_amount_selection)
SELECT m.name, m.sequence, m.create_uid, m.create_date, m.write_uid, m.write_date,
       m.primary_payment_method_id, m.code, m.support_refund, m.active, m.support_tokenization,
       m.support_express_checkout, m.support_manual_capture, u.provider_id, m.allow_amount_selection
  FROM (SELECT provider_id, payment_method_id FROM payment_transaction
        UNION
        SELECT provider_id, payment_method_id FROM payment_token) u
  JOIN payment_method m ON m.id = u.payment_method_id AND m.provider_id IS NULL
ON CONFLICT (provider_id, code) DO NOTHING;
-- 2. Transactions and tokens move to the method of their own provider.
UPDATE payment_transaction t SET payment_method_id = n.id
  FROM payment_method o, payment_method n
 WHERE o.id = t.payment_method_id AND o.provider_id IS NULL
   AND n.provider_id = t.provider_id AND n.code = o.code;
UPDATE payment_token t SET payment_method_id = n.id
  FROM payment_method o, payment_method n
 WHERE o.id = t.payment_method_id AND o.provider_id IS NULL
   AND n.provider_id = t.provider_id AND n.code = o.code;
-- 3. The country and currency restrictions of the old methods go with the copies.
INSERT INTO payment_method_res_country_rel (payment_method_id, res_country_id)
SELECT n.id, r.res_country_id
  FROM payment_method n
  JOIN payment_method o ON o.code = n.code AND o.provider_id IS NULL
  JOIN payment_method_res_country_rel r ON r.payment_method_id = o.id
 WHERE n.provider_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM payment_method_res_country_rel x WHERE x.payment_method_id = n.id)
ON CONFLICT DO NOTHING;
INSERT INTO payment_method_res_currency_rel (payment_method_id, res_currency_id)
SELECT n.id, r.res_currency_id
  FROM payment_method n
  JOIN payment_method o ON o.code = n.code AND o.provider_id IS NULL
  JOIN payment_method_res_currency_rel r ON r.payment_method_id = o.id
 WHERE n.provider_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM payment_method_res_currency_rel x WHERE x.payment_method_id = n.id)
ON CONFLICT DO NOTHING;
-- 4. Brand methods point at the method of the same provider as well.
UPDATE payment_method n SET primary_payment_method_id = p.id
  FROM payment_method o, payment_method p
 WHERE n.provider_id IS NOT NULL AND o.id = n.primary_payment_method_id AND o.provider_id IS NULL
   AND p.provider_id = n.provider_id AND p.code = o.code;
-- 5. What is left of the old methods is not in use any more.
DELETE FROM payment_method WHERE provider_id IS NULL;
"""


@openupgrade.migrate()
def migrate(env, version):
    openupgrade.logged_query(env.cr, _CONVERT_PAYMENT_METHODS)

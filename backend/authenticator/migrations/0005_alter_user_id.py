# Custom migration: alter users.id from bigint to uuid
# PostgreSQL cannot cast bigint → uuid directly, so we use raw SQL to:
#   1. Enable pgcrypto for gen_random_uuid()
#   2. Drop all FK constraints that reference users(id)
#   3. Add a new uuid column, populate it, swap it as primary key
#   4. Update uuid FK columns in all referencing tables
#   5. Re-add FK constraints

from django.db import migrations


FORWARD_SQL = """
-- 1. Enable pgcrypto
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 2. Add temporary uuid column to users and populate it
ALTER TABLE users ADD COLUMN new_id uuid DEFAULT gen_random_uuid();
UPDATE users SET new_id = gen_random_uuid();
ALTER TABLE users ALTER COLUMN new_id SET NOT NULL;

-- 3. Drop all FK constraints that reference users(id)
ALTER TABLE bank_accounts                   DROP CONSTRAINT bank_accounts_user_id_c753e843_fk_users_id;
ALTER TABLE django_admin_log                DROP CONSTRAINT django_admin_log_user_id_c564eba6_fk_users_id;
ALTER TABLE email_verification_tokens       DROP CONSTRAINT email_verification_tokens_user_id_3cbf3e2d_fk_users_id;
ALTER TABLE kyc_verifications               DROP CONSTRAINT kyc_verifications_user_id_ccdf0274_fk_users_id;
ALTER TABLE ngn_wallets                     DROP CONSTRAINT ngn_wallets_user_id_4347b58c_fk_users_id;
ALTER TABLE password_reset_tokens           DROP CONSTRAINT password_reset_tokens_user_id_0aeaaad3_fk_users_id;
ALTER TABLE token_blacklist_outstandingtoken DROP CONSTRAINT token_blacklist_outstandingtoken_user_id_83bc629a_fk_users_id;
ALTER TABLE users_groups                    DROP CONSTRAINT users_groups_user_id_f500bee5_fk_users_id;
ALTER TABLE users_user_permissions          DROP CONSTRAINT users_user_permissions_user_id_92473840_fk_users_id;

-- 4. Add uuid FK columns to every referencing table and populate them
ALTER TABLE bank_accounts                    ADD COLUMN new_user_id uuid;
UPDATE bank_accounts ba SET new_user_id = u.new_id FROM users u WHERE u.id = ba.user_id;

ALTER TABLE django_admin_log                 ADD COLUMN new_user_id uuid;
UPDATE django_admin_log dal SET new_user_id = u.new_id FROM users u WHERE u.id = dal.user_id;

ALTER TABLE email_verification_tokens        ADD COLUMN new_user_id uuid;
UPDATE email_verification_tokens evt SET new_user_id = u.new_id FROM users u WHERE u.id = evt.user_id;

ALTER TABLE kyc_verifications                ADD COLUMN new_user_id uuid;
UPDATE kyc_verifications kv SET new_user_id = u.new_id FROM users u WHERE u.id = kv.user_id;

ALTER TABLE ngn_wallets                      ADD COLUMN new_user_id uuid;
UPDATE ngn_wallets nw SET new_user_id = u.new_id FROM users u WHERE u.id = nw.user_id;

ALTER TABLE password_reset_tokens            ADD COLUMN new_user_id uuid;
UPDATE password_reset_tokens pt SET new_user_id = u.new_id FROM users u WHERE u.id = pt.user_id;

ALTER TABLE token_blacklist_outstandingtoken ADD COLUMN new_user_id uuid;
UPDATE token_blacklist_outstandingtoken tbo SET new_user_id = u.new_id FROM users u WHERE u.id = tbo.user_id;

ALTER TABLE users_groups                     ADD COLUMN new_user_id uuid;
UPDATE users_groups ug SET new_user_id = u.new_id FROM users u WHERE u.id = ug.user_id;

ALTER TABLE users_user_permissions           ADD COLUMN new_user_id uuid;
UPDATE users_user_permissions uup SET new_user_id = u.new_id FROM users u WHERE u.id = uup.user_id;

-- 5. Swap the primary key on users
ALTER TABLE users DROP CONSTRAINT users_pkey;
ALTER TABLE users DROP COLUMN id;
ALTER TABLE users RENAME COLUMN new_id TO id;
ALTER TABLE users ADD PRIMARY KEY (id);
ALTER TABLE users ALTER COLUMN id DROP DEFAULT;

-- 6. Swap old integer FK columns with the new uuid columns
-- bank_accounts
ALTER TABLE bank_accounts DROP COLUMN user_id;
ALTER TABLE bank_accounts RENAME COLUMN new_user_id TO user_id;
ALTER TABLE bank_accounts ALTER COLUMN user_id SET NOT NULL;

-- django_admin_log
ALTER TABLE django_admin_log DROP COLUMN user_id;
ALTER TABLE django_admin_log RENAME COLUMN new_user_id TO user_id;

-- email_verification_tokens
ALTER TABLE email_verification_tokens DROP COLUMN user_id;
ALTER TABLE email_verification_tokens RENAME COLUMN new_user_id TO user_id;
ALTER TABLE email_verification_tokens ALTER COLUMN user_id SET NOT NULL;

-- kyc_verifications
ALTER TABLE kyc_verifications DROP COLUMN user_id;
ALTER TABLE kyc_verifications RENAME COLUMN new_user_id TO user_id;
ALTER TABLE kyc_verifications ALTER COLUMN user_id SET NOT NULL;

-- ngn_wallets
ALTER TABLE ngn_wallets DROP COLUMN user_id;
ALTER TABLE ngn_wallets RENAME COLUMN new_user_id TO user_id;
ALTER TABLE ngn_wallets ALTER COLUMN user_id SET NOT NULL;

-- password_reset_tokens
ALTER TABLE password_reset_tokens DROP COLUMN user_id;
ALTER TABLE password_reset_tokens RENAME COLUMN new_user_id TO user_id;
ALTER TABLE password_reset_tokens ALTER COLUMN user_id SET NOT NULL;

-- token_blacklist_outstandingtoken
ALTER TABLE token_blacklist_outstandingtoken DROP COLUMN user_id;
ALTER TABLE token_blacklist_outstandingtoken RENAME COLUMN new_user_id TO user_id;

-- users_groups
ALTER TABLE users_groups DROP COLUMN user_id;
ALTER TABLE users_groups RENAME COLUMN new_user_id TO user_id;
ALTER TABLE users_groups ALTER COLUMN user_id SET NOT NULL;

-- users_user_permissions
ALTER TABLE users_user_permissions DROP COLUMN user_id;
ALTER TABLE users_user_permissions RENAME COLUMN new_user_id TO user_id;
ALTER TABLE users_user_permissions ALTER COLUMN user_id SET NOT NULL;

-- 7. Re-add FK constraints with the original Django-generated names
ALTER TABLE bank_accounts
    ADD CONSTRAINT bank_accounts_user_id_c753e843_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE django_admin_log
    ADD CONSTRAINT django_admin_log_user_id_c564eba6_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE email_verification_tokens
    ADD CONSTRAINT email_verification_tokens_user_id_3cbf3e2d_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE kyc_verifications
    ADD CONSTRAINT kyc_verifications_user_id_ccdf0274_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE ngn_wallets
    ADD CONSTRAINT ngn_wallets_user_id_4347b58c_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_0aeaaad3_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE token_blacklist_outstandingtoken
    ADD CONSTRAINT token_blacklist_outstandingtoken_user_id_83bc629a_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE users_groups
    ADD CONSTRAINT users_groups_user_id_f500bee5_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE users_user_permissions
    ADD CONSTRAINT users_user_permissions_user_id_92473840_fk_users_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED;
"""

REVERSE_SQL = "SELECT 'Reversing UUID migration is not supported. Restore from backup.';"


class Migration(migrations.Migration):

    dependencies = [
        ('authenticator', '0004_emailverificationtoken'),
    ]

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]

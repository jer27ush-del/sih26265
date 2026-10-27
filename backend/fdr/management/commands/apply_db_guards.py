"""Installs database-level protection on the audit table (PostgreSQL only).

After this runs, even a direct SQL UPDATE or DELETE on fdr_auditlog fails.
The application account should also be granted only INSERT and SELECT on that table.
"""
from django.core.management.base import BaseCommand
from django.db import connection

FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION fdr_block_audit_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'audit log is append-only';
END;
$$ LANGUAGE plpgsql;
"""
TRIGGER_SQL = """
DROP TRIGGER IF EXISTS fdr_auditlog_append_only ON fdr_auditlog;
CREATE TRIGGER fdr_auditlog_append_only
BEFORE UPDATE OR DELETE ON fdr_auditlog
FOR EACH ROW EXECUTE FUNCTION fdr_block_audit_change();
"""


class Command(BaseCommand):
    help = 'Make the audit table append-only at the database level (PostgreSQL).'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            self.stdout.write('Skipped: database guards need PostgreSQL. The application still refuses audit changes.')
            return
        with connection.cursor() as cursor:
            cursor.execute(FUNCTION_SQL)
            cursor.execute(TRIGGER_SQL)
        self.stdout.write(self.style.SUCCESS('Audit table is now append-only in the database.'))

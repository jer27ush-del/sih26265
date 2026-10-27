"""API and database tests. Run with: python manage.py test fdr  (needs the database; see backend/README.md).

These cover the rules that matter most: role and institution isolation, transactional audit,
the bank-confirmation gate, partial bulk import, and the append-only audit log.
"""
from datetime import date
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from fdr import services
from fdr.domain import DomainError
from fdr.errors import Forbidden, NotFound
from fdr.models import FDR, AuditLog, Institution, MaturityEmailReminder, SystemSettings

User = get_user_model()


class SeededTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', verbosity=0)
        cls.inst = User.objects.get(email='institution@demo.test')
        cls.officer = User.objects.get(email='officer@demo.test')
        cls.admin = User.objects.get(email='admin@demo.test')
        cls.auditor = User.objects.get(email='auditor@demo.test')
        cls.other_fdr = FDR.objects.get(fdr_number='DEMO-FDR-1002')   # belongs to DEMO002
        cls.own_fdr = FDR.objects.get(fdr_number='DEMO-FDR-1001')     # belongs to DEMO001


class RuleAndWorkflowTests(SeededTestCase):
    def test_institution_user_cannot_see_another_institutions_fdr(self):
        with self.assertRaises(NotFound):
            services.transition(self.inst, self.other_fdr.id, 'Corrected')

    def test_verified_requires_bank_confirmation(self):
        fdr = self.other_fdr
        with self.assertRaisesRegex(DomainError, 'bank confirmation'):
            services.transition(self.officer, fdr.id, 'Verified', 'checked')

    def test_bank_confirmation_then_verify_writes_audit_in_same_transaction(self):
        fdr = self.other_fdr
        services.record_bank_confirmation(self.officer, fdr.id, {
            'date': date(2026, 10, 20), 'officer': 'Ravi', 'mode': 'Email', 'reference': 'LTR-9'})
        before = AuditLog.objects.count()
        services.transition(self.officer, fdr.id, 'Verified', 'Confirmed with bank')
        fdr.refresh_from_db()
        self.assertEqual(fdr.status, 'Verified')
        self.assertGreater(AuditLog.objects.count(), before)

    def test_officer_cannot_close_a_release(self):
        services.add_request(self.inst, self.own_fdr.id, 'release', 'Early need')
        self.own_fdr.refresh_from_db()
        self.assertEqual(self.own_fdr.status, 'Release Requested')
        with self.assertRaises(Forbidden):
            services.transition(self.officer, self.own_fdr.id, 'Released / Closed')

    def test_release_needs_recommendation_before_approval(self):
        req = services.add_request(self.inst, self.own_fdr.id, 'release', 'Early need')
        with self.assertRaisesRegex(DomainError, 'recommended'):
            services.decide_request(self.admin, req.id, 'approve', 'ok')

    def test_bulk_import_keeps_good_rows_and_reports_bad_ones(self):
        rows = [
            ['DEMO001', 'IMP-A', 'Sample National Bank', 'Chennai, Main', '500000', '2026-01-15', '2027-01-15', '6.5', 'cumulative', ''],
            ['DEMO001', 'IMP-A', 'Sample National Bank', 'Chennai', '1000', '2026-01-15', '2027-01-15', '6', 'cumulative', ''],
            ['DEMO999', 'IMP-B', 'Sample National Bank', 'Chennai', '1000', '2026-01-15', '2027-01-15', '6', 'cumulative', ''],
        ]
        result = services.import_rows(self.admin, rows)
        self.assertEqual(result['imported'], 1)
        self.assertEqual([s['line'] for s in result['skipped']], [2, 3])


class DatabaseGuardTests(SeededTestCase):
    def test_audit_rows_cannot_be_changed_by_the_application(self):
        entry = AuditLog.objects.first()
        with self.assertRaises(PermissionError):
            entry.action = 'tampered'
            entry.save()
        with self.assertRaises(PermissionError):
            AuditLog.objects.filter(pk=entry.pk).update(action='tampered')
        with self.assertRaises(PermissionError):
            entry.delete()

    def test_duplicate_fdr_number_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FDR.objects.create(fdr_number='demo-fdr-1001', bank='sample national bank',
                                   branch='x', institution=self.own_fdr.institution, amount_paise=100,
                                   issue_date=date(2026, 1, 1), maturity_date=date(2027, 1, 1),
                                   category='x', status='Submitted')

    def test_maturity_must_follow_issue_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                FDR.objects.create(fdr_number='BAD-1', bank='B', branch='x', institution=self.own_fdr.institution,
                                   amount_paise=100, issue_date=date(2027, 1, 1), maturity_date=date(2026, 1, 1),
                                   category='x', status='Submitted')


class MaturityEmailTests(SeededTestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       DEFAULT_FROM_EMAIL='fdr@example.test')
    def test_sends_once_at_each_configured_milestone_to_institution_contact(self):
        today = date(2026, 10, 27)
        institution = self.own_fdr.institution
        institution.email = 'contact@example.test'
        institution.save(update_fields=['email'])
        self.own_fdr.status = 'Active'
        self.own_fdr.maturity_date = today + timedelta(days=90)
        self.own_fdr.save(update_fields=['status', 'maturity_date'])

        for days in (90, 60, 30):
            self.own_fdr.maturity_date = today + timedelta(days=days)
            self.own_fdr.save(update_fields=['maturity_date'])
            result = services.run_daily_jobs(today=today)
            self.assertEqual(result['emailsSent'], 1)
            self.assertEqual(mail.outbox[-1].to, ['contact@example.test'])
            self.assertIn(f'{days} days', mail.outbox[-1].subject)
            due_date = self.own_fdr.maturity_date.strftime('%d %B %Y').lstrip('0')
            self.assertIn(due_date, mail.outbox[-1].body)

        self.assertEqual(MaturityEmailReminder.objects.filter(fdr=self.own_fdr).count(), 3)
        self.assertEqual(services.run_daily_jobs(today=today)['emailsSent'], 0)
        self.assertEqual(len(mail.outbox), 3)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                       DEFAULT_FROM_EMAIL='fdr@example.test')
    def test_does_not_send_before_a_milestone_or_without_contact_email(self):
        today = date(2026, 10, 27)
        self.own_fdr.status = 'Active'
        self.own_fdr.maturity_date = today + timedelta(days=89)
        self.own_fdr.institution.email = 'contact@example.test'
        self.own_fdr.institution.save(update_fields=['email'])
        self.own_fdr.save(update_fields=['status', 'maturity_date'])

        result = services.run_daily_jobs(today=today)

        self.assertEqual(result['emailsSent'], 0)
        self.assertEqual(mail.outbox, [])

        self.own_fdr.maturity_date = today + timedelta(days=90)
        self.own_fdr.save(update_fields=['maturity_date'])
        self.own_fdr.institution.email = ''
        self.own_fdr.institution.save(update_fields=['email'])

        result = services.run_daily_jobs(today=today)

        self.assertEqual(result['emailsSent'], 0)
        self.assertEqual(mail.outbox, [])


class ApiTests(SeededTestCase):
    def setUp(self):
        self.client = APIClient()

    def login(self, email):
        token = self.client.post('/api/auth/login/', {'email': email, 'password': 'demo123'}, format='json')
        self.assertEqual(token.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.json()['token']}")

    def test_anonymous_requests_are_refused(self):
        self.assertEqual(self.client.get('/api/fdrs/').status_code, 401)

    def test_institution_list_is_scoped(self):
        self.login('institution@demo.test')
        codes = [i['code'] for i in self.client.get('/api/institutions/').json()]
        self.assertEqual(codes, ['DEMO001'])

    def test_fdr_detail_for_other_institution_is_not_found(self):
        self.login('institution@demo.test')
        self.assertEqual(self.client.get(f'/api/fdrs/{self.other_fdr.id}/').status_code, 404)

    def test_auditor_cannot_transition(self):
        self.login('auditor@demo.test')
        response = self.client.post(f'/api/fdrs/{self.own_fdr.id}/transition/', {'status': 'Verified', 'reason': 'x'}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_settings_are_admin_only(self):
        self.login('officer@demo.test')
        self.assertEqual(self.client.put('/api/settings/', {'maturityThresholds': [30]}, format='json').status_code, 403)

    def test_workspace_returns_store_shape(self):
        self.login('admin@demo.test')
        body = self.client.get('/api/workspace/').json()
        for key in ('institutions', 'users', 'fdrs', 'verifications', 'queries', 'requests', 'auditLogs', 'settings'):
            self.assertIn(key, body)
        self.assertGreaterEqual(len(body['fdrs']), 3)

    def test_demo_switch_disabled_outside_demo_mode(self):
        from django.test import override_settings
        with override_settings(DEMO_MODE=False):
            response = self.client.post('/api/auth/demo-switch/', {'userId': str(self.admin.id)}, format='json')
            self.assertEqual(response.status_code, 403)

    def test_settings_row_exists(self):
        self.assertTrue(SystemSettings.objects.filter(pk=1).exists())

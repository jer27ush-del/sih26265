"""Tests for the pure rules. Run with: python manage.py test fdr.tests.test_domain  (or python -m unittest fdr.tests.test_domain)."""
import unittest
from datetime import date

from fdr import domain as d


SETTINGS = {
    'allowedDocumentTypes': ['application/pdf', 'image/png', 'image/jpeg'],
    'amountLimitsPaise': {'min': 100, 'max': 100000000000},
    'minimumTenureDays': 365,
}
GOOD_FDR = {'fdr_number': 'TEST-1', 'bank': 'Sample National Bank', 'branch': 'Chennai',
            'amount_paise': 50000000, 'issue_date': '2026-01-15', 'maturity_date': '2027-01-15'}
PDF = [{'mime': 'application/pdf', 'size': 2048, 'active': True}]
TODAY = date(2026, 10, 27)


class MoneyTests(unittest.TestCase):
    def test_indian_grouping_and_decimals_are_exact(self):
        self.assertEqual(d.rupees_to_paise('5,00,000'), 50000000)
        self.assertEqual(d.rupees_to_paise('1234.5'), 123450)
        self.assertEqual(d.rupees_to_paise('99.99'), 9999)

    def test_bad_amounts_are_rejected(self):
        for bad in ('-5', 'abc', '1.234', ''):
            with self.assertRaises(d.DomainError):
                d.rupees_to_paise(bad)

    def test_paise_format(self):
        self.assertEqual(d.paise_to_decimal(50000000), '500000.00')
        self.assertEqual(d.paise_to_decimal(5), '0.05')


class StatusMachineTests(unittest.TestCase):
    def test_unlisted_transition_is_refused(self):
        self.assertEqual(d.transition_denial_reason('Submitted', 'Verified', d.ROLE_ADMIN),
                         'Transition Submitted → Verified is not allowed.')

    def test_officer_cannot_close_a_release(self):
        self.assertEqual(d.transition_denial_reason('Release Requested', 'Released / Closed', d.ROLE_OFFICER),
                         'Your role cannot perform this transition.')
        self.assertIsNone(d.transition_denial_reason('Release Requested', 'Released / Closed', d.ROLE_ADMIN))

    def test_premature_withdrawal_path_exists_for_institutions(self):
        self.assertTrue(d.is_transition_allowed('Active', 'Release Requested', d.ROLE_INSTITUTION))

    def test_maturity_alone_cannot_release_a_deposit(self):
        self.assertFalse(d.is_transition_allowed('Matured', 'Released / Closed', d.SYSTEM))


class PermissionTests(unittest.TestCase):
    def test_audit_visibility(self):
        self.assertFalse(d.can_view_audit(d.ROLE_INSTITUTION))
        self.assertTrue(d.can_view_audit(d.ROLE_OFFICER))
        self.assertTrue(d.can_view_audit(d.ROLE_AUDITOR))

    def test_release_needs_a_recommendation_and_separate_people(self):
        self.assertFalse(d.can_approve_release(d.ROLE_ADMIN, 'a', 'inst', None))
        self.assertTrue(d.can_approve_release(d.ROLE_ADMIN, 'a', 'inst', 'off'))
        self.assertFalse(d.can_approve_release(d.ROLE_ADMIN, 'a', 'inst', 'a'))


class DateTests(unittest.TestCase):
    def test_days_and_states(self):
        self.assertEqual(d.days_to_maturity(date(2026, 10, 27), TODAY), 0)
        self.assertEqual(d.derive_maturity_state(date(2026, 10, 27), [30], TODAY), 'Matured')
        self.assertEqual(d.derive_maturity_state(date(2026, 10, 25), [30], TODAY), 'Overdue')
        self.assertEqual(d.derive_maturity_state(date(2026, 12, 1), [90, 60, 30], TODAY), 'Nearing Maturity')

    def test_reference_key_ignores_case_and_spaces(self):
        self.assertEqual(d.reference_key('  demo-1 ', 'Bank'), d.reference_key('DEMO-1', 'bank '))


class FieldValidationTests(unittest.TestCase):
    def test_maturity_must_follow_issue(self):
        with self.assertRaisesRegex(d.DomainError, 'after issue date'):
            d.validate_fdr_fields({**GOOD_FDR, 'category': 'Security Deposit', 'maturity_date': '2026-01-01', 'interest_rate': 6})

    def test_good_fields_pass(self):
        d.validate_fdr_fields({**GOOD_FDR, 'category': 'Security Deposit', 'interest_rate': 6.5})

    def test_document_type_and_size(self):
        with self.assertRaisesRegex(d.DomainError, 'Only PDF'):
            d.validate_document('application/x-msdownload', 100, SETTINGS['allowedDocumentTypes'], 10)
        with self.assertRaisesRegex(d.DomainError, 'larger'):
            d.validate_document('application/pdf', 11, SETTINGS['allowedDocumentTypes'], 10)

    def test_settings_validation(self):
        base = {'maturityThresholds': [90, 60, 30], 'minimumTenureDays': 365, 'documentMaxBytes': 10,
                'banks': ['A'], 'categories': ['B']}
        d.validate_settings(base)
        with self.assertRaisesRegex(d.DomainError, 'thresholds'):
            d.validate_settings({**base, 'maturityThresholds': [0]})


class VerificationRuleTests(unittest.TestCase):
    def run_rules(self, **overrides):
        args = dict(fdr=GOOD_FDR, institution_exists=True, documents=PDF, duplicate_exists=False,
                    settings=SETTINGS, bank_confirmed=False, today=TODAY)
        args.update(overrides)
        return d.run_verification_rules(**args)

    def test_clean_record_passes_all_but_bank_confirmation(self):
        results = self.run_rules()
        self.assertEqual(set(results), set(d.RULE_NAMES))
        self.assertEqual(results['bank_confirmation'], 'fail')
        self.assertFalse(d.is_flagged(results))

    def test_missing_document_flags_the_record(self):
        results = self.run_rules(documents=[])
        self.assertEqual(results['required_fields'], 'fail')
        self.assertEqual(results['document_quality'], 'warning')
        self.assertTrue(d.is_flagged(results))

    def test_duplicate_fails(self):
        self.assertEqual(self.run_rules(duplicate_exists=True)['duplicate_reference'], 'fail')

    def test_future_issue_date_warns(self):
        future = {**GOOD_FDR, 'issue_date': '2027-01-01', 'maturity_date': '2028-01-01'}
        self.assertEqual(self.run_rules(fdr=future)['date_logic'], 'warning')

    def test_short_tenure_warns(self):
        short = {**GOOD_FDR, 'maturity_date': '2026-03-01'}
        self.assertEqual(self.run_rules(fdr=short)['tenure_validity'], 'warning')

    def test_bank_confirmation_passes_once_confirmed(self):
        self.assertEqual(self.run_rules(bank_confirmed=True)['bank_confirmation'], 'pass')


class ImportTests(unittest.TestCase):
    def test_quoted_comma_survives_parsing(self):
        rows = d.parse_csv_text('a,b\n"x, y",z\n')
        self.assertEqual(rows, [['a', 'b'], ['x, y', 'z']])

    def test_row_mapping(self):
        cells = ['DEMO001', 'IMP-1', 'Bank', 'Chennai, Main', '2,500.50', '2026-02-01', '2028-02-01', '7', 'periodic', '']
        parsed = d.parse_import_row(cells, 2, 'Security Deposit')
        self.assertEqual(parsed['amount_paise'], 250050)
        self.assertEqual(parsed['branch'], 'Chennai, Main')
        self.assertEqual(parsed['payout_type'], 'periodic')
        self.assertEqual(parsed['category'], 'Security Deposit')

    def test_bad_payout_is_refused(self):
        cells = ['DEMO001', 'IMP-1', 'Bank', 'x', '1000', '2026-01-01', '2027-01-01', '6', 'monthly', '']
        with self.assertRaisesRegex(d.DomainError, 'cumulative or periodic'):
            d.parse_import_row(cells, 2, 'x')


if __name__ == '__main__':
    unittest.main()

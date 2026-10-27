"""Pure business rules for the AICTE FDR portal.

This module deliberately imports nothing from Django. Every rule that decides
whether a record may change lives here, so it can be unit-tested without a
database. The Django services call these functions inside database
transactions; the React frontend never decides anything on its own.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date


class DomainError(Exception):
    """A business-rule violation. The message is safe to show to the user."""


# ---------------------------------------------------------------- roles & permissions
ROLE_INSTITUTION = 'institution_user'
ROLE_OFFICER = 'scrutiny_officer'
ROLE_ADMIN = 'administrator'
ROLE_AUDITOR = 'auditor'
ROLES = (ROLE_INSTITUTION, ROLE_OFFICER, ROLE_ADMIN, ROLE_AUDITOR)
SYSTEM = 'system'

_PERMISSIONS = {
    ROLE_INSTITUTION: {'view_fdrs', 'register_fdr', 'import_fdrs', 'reply_query', 'submit_request', 'view_reports'},
    ROLE_OFFICER: {'view_fdrs', 'review_fdr', 'recommend_release', 'view_reports', 'view_limited_audit_logs'},
    ROLE_ADMIN: {'view_fdrs', 'register_fdr', 'import_fdrs', 'manage_institutions', 'review_fdr', 'submit_request',
                 'recommend_release', 'approve_release', 'change_settings', 'view_reports', 'view_audit_logs'},
    ROLE_AUDITOR: {'view_fdrs', 'view_reports', 'view_audit_logs'},
}


def can(role: str, action: str) -> bool:
    return action in _PERMISSIONS.get(role, set())


def can_view_audit(role: str) -> bool:
    return can(role, 'view_audit_logs') or can(role, 'view_limited_audit_logs')


def can_approve_release(role: str, user_id: str, submitted_by: str | None, recommended_by: str | None) -> bool:
    """Separation of duties: an administrator approves only a recommended request they did not submit or recommend."""
    return (role == ROLE_ADMIN and recommended_by is not None
            and user_id != submitted_by and user_id != recommended_by)


# ---------------------------------------------------------------- status machine
TRANSITIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ('Submitted', 'Under Verification', (ROLE_INSTITUTION, ROLE_OFFICER, ROLE_ADMIN, SYSTEM)),
    ('Under Verification', 'Query Raised', (ROLE_OFFICER, ROLE_ADMIN)),
    ('Under Verification', 'Verified', (ROLE_OFFICER, ROLE_ADMIN)),
    ('Under Verification', 'Rejected', (ROLE_OFFICER, ROLE_ADMIN)),
    ('Query Raised', 'Corrected', (ROLE_INSTITUTION,)),
    ('Corrected', 'Under Verification', (ROLE_INSTITUTION, ROLE_OFFICER, SYSTEM)),
    ('Verified', 'Active', (SYSTEM,)),
    ('Active', 'Nearing Maturity', (SYSTEM,)),
    ('Active', 'Release Requested', (ROLE_INSTITUTION,)),
    ('Nearing Maturity', 'Matured', (SYSTEM,)),
    ('Nearing Maturity', 'Renewed', (ROLE_INSTITUTION, ROLE_OFFICER)),
    ('Nearing Maturity', 'Release Requested', (ROLE_INSTITUTION,)),
    ('Matured', 'Renewed', (ROLE_INSTITUTION, ROLE_OFFICER)),
    ('Matured', 'Release Requested', (ROLE_INSTITUTION,)),
    ('Renewed', 'Released / Closed', (SYSTEM,)),
    ('Release Requested', 'Released / Closed', (ROLE_ADMIN,)),
    ('Release Requested', 'Active', (ROLE_ADMIN,)),
)

FDR_STATUSES = tuple(sorted({s for f, t, _ in TRANSITIONS for s in (f, t)} | {'Rejected'}))
TERMINAL_STATUSES = ('Renewed', 'Released / Closed', 'Rejected')
RELEASE_ELIGIBLE = ('Verified', 'Active', 'Nearing Maturity', 'Matured')
RENEWAL_ELIGIBLE = ('Nearing Maturity', 'Matured')
OPEN_REQUEST_STATUSES = ('Submitted', 'Recommended')


def is_transition_allowed(src: str, dst: str, role: str) -> bool:
    return any(f == src and t == dst and role in roles for f, t, roles in TRANSITIONS)


def transition_denial_reason(src: str, dst: str, role: str) -> str | None:
    if is_transition_allowed(src, dst, role):
        return None
    listed = any(f == src and t == dst for f, t, _ in TRANSITIONS)
    return 'Your role cannot perform this transition.' if listed else f'Transition {src} → {dst} is not allowed.'


# ---------------------------------------------------------------- money & dates
_RUPEES = re.compile(r'^(\d+)(?:\.(\d{1,2}))?$')


def rupees_to_paise(text: str) -> int:
    """Converts user input such as '5,00,000' or '1234.5' into integer paise without floating point."""
    cleaned = str(text).replace(',', '').strip()
    match = _RUPEES.match(cleaned)
    if not match:
        raise DomainError(f'Enter an amount in rupees with at most two decimals (got "{text}").')
    paise = int(match.group(1)) * 100 + int((match.group(2) or '').ljust(2, '0'))
    return paise


def paise_to_decimal(paise: int) -> str:
    sign = '-' if paise < 0 else ''
    absolute = abs(paise)
    return f'{sign}{absolute // 100}.{absolute % 100:02d}'


def parse_iso_date(value: str, field: str) -> date:
    try:
        if len(str(value)) != 10:
            raise ValueError
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DomainError(f'Enter a valid {field} (YYYY-MM-DD).') from exc


def days_to_maturity(maturity: date, today: date) -> int:
    return (maturity - today).days


def derive_maturity_state(maturity: date, thresholds: list[int], today: date, has_outcome: bool = False) -> str:
    days = days_to_maturity(maturity, today)
    if days < 0 and not has_outcome:
        return 'Overdue'
    if days <= 0:
        return 'Matured'
    if any(days <= t for t in thresholds):
        return 'Nearing Maturity'
    return 'Active'


def reference_key(fdr_number: str, bank: str) -> tuple[str, str]:
    """The uniqueness key for an FDR: case- and whitespace-insensitive."""
    return fdr_number.strip().lower(), bank.strip().lower()


# ---------------------------------------------------------------- validation
REQUIRED_TEXT = ('fdr_number', 'bank', 'branch', 'category')


def validate_fdr_fields(fields: dict) -> None:
    """Checks a registration's own fields. Duplicates and institution status are checked by the service."""
    for name in REQUIRED_TEXT:
        if not str(fields.get(name, '')).strip():
            raise DomainError(f'Enter the {name.replace("_", " ")}.')
    amount = fields.get('amount_paise')
    if not isinstance(amount, int) or amount <= 0:
        raise DomainError('Amount must be greater than zero.')
    issue = parse_iso_date(fields.get('issue_date', ''), 'issue date')
    maturity = parse_iso_date(fields.get('maturity_date', ''), 'maturity date')
    if maturity <= issue:
        raise DomainError('Maturity date must be after issue date.')
    rate = fields.get('interest_rate', 0)
    if not isinstance(rate, (int, float)) or rate < 0:
        raise DomainError('Interest rate must be zero or more.')


_SIGNATURES = (
    (b'%PDF-', 'application/pdf'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'\xff\xd8\xff', 'image/jpeg'),
)


def sniff_mime(head: bytes) -> str | None:
    """Identifies a file from its first bytes. The browser-supplied type and the extension are not trusted."""
    for signature, mime in _SIGNATURES:
        if head.startswith(signature):
            return mime
    return None


def validate_document(mime: str, size: int, allowed: list[str], max_bytes: int) -> None:
    if mime not in allowed:
        raise DomainError('Only PDF, PNG or JPEG files are accepted.')
    if size <= 0 or size > max_bytes:
        raise DomainError('The file is empty or larger than the configured limit.')


def validate_settings(data: dict) -> None:
    thresholds = data.get('maturityThresholds', [])
    if not thresholds or any(not isinstance(d, int) or d <= 0 for d in thresholds):
        raise DomainError('Maturity thresholds must be positive whole numbers of days.')
    tenure = data.get('minimumTenureDays')
    if not isinstance(tenure, int) or tenure < 0:
        raise DomainError('Minimum tenure must be zero or more whole days.')
    max_bytes = data.get('documentMaxBytes')
    if not isinstance(max_bytes, int) or max_bytes <= 0:
        raise DomainError('Maximum document size must be a positive number of bytes.')
    if not data.get('banks'):
        raise DomainError('Add at least one bank.')
    if not data.get('categories'):
        raise DomainError('Add at least one deposit category.')


# ---------------------------------------------------------------- automated checks
RULE_NAMES = ('required_fields', 'duplicate_reference', 'date_logic', 'tenure_validity',
              'amount_range', 'document_quality', 'bank_confirmation')


def run_verification_rules(*, fdr: dict, institution_exists: bool, documents: list[dict],
                           duplicate_exists: bool, settings: dict, bank_confirmed: bool,
                           today: date) -> dict[str, str]:
    """The seven automated checks from the spec. Returns pass / warning / fail per rule."""
    valid_docs = [d for d in documents if d.get('active', True) and d.get('size', 0) > 0
                  and d.get('mime') in settings.get('allowedDocumentTypes', [])]
    issue = date.fromisoformat(fdr['issue_date'])
    maturity = date.fromisoformat(fdr['maturity_date'])
    tenure = days_to_maturity(maturity, issue)
    amount = fdr['amount_paise']
    limits = settings.get('amountLimitsPaise', {'min': 1, 'max': 10**12})
    required_ok = bool(fdr['fdr_number'].strip() and fdr['bank'].strip() and fdr['branch'].strip()
                       and institution_exists and valid_docs)
    return {
        'required_fields': 'pass' if required_ok else 'fail',
        'duplicate_reference': 'fail' if duplicate_exists else 'pass',
        'date_logic': 'pass' if maturity > issue and issue <= today else 'warning',
        'tenure_validity': 'pass' if tenure >= settings.get('minimumTenureDays', 0) else 'warning',
        'amount_range': 'pass' if limits['min'] <= amount <= limits['max'] else 'warning',
        'document_quality': 'pass' if valid_docs else 'warning',
        'bank_confirmation': 'pass' if bank_confirmed else 'fail',
    }


def is_flagged(results: dict[str, str]) -> bool:
    """Bank confirmation can only pass after review, so it does not raise the on-submission flag."""
    return any(rule != 'bank_confirmation' and flag != 'pass' for rule, flag in results.items())


# ---------------------------------------------------------------- bulk import
IMPORT_COLUMNS = ('institutionCode', 'fdrNumber', 'bank', 'branch', 'amountINR', 'issueDate',
                  'maturityDate', 'interestRate', 'payoutType', 'category')


def parse_csv_text(text: str) -> list[list[str]]:
    """RFC 4180 parsing: quoted commas, escaped quotes and line breaks inside quotes are handled."""
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff')))
    return [row for row in reader if any(cell.strip() for cell in row)]


def parse_import_row(cells: list[str], line: int, category_default: str) -> dict:
    """Maps one CSV row to registration fields. Raises DomainError with a plain reason."""
    if len(cells) < 7:
        raise DomainError('Row needs at least 7 columns (institution code to maturity date).')
    cell = [c.strip() for c in cells] + [''] * 10
    payout = cell[8].lower()
    if payout not in ('', 'cumulative', 'periodic'):
        raise DomainError('Payout type must be cumulative or periodic.')
    try:
        amount = rupees_to_paise(cell[4])
    except DomainError:
        raise DomainError(f'Invalid amount "{cell[4]}".')
    rate_text = cell[7]
    try:
        rate = float(rate_text) if rate_text else 0.0
    except ValueError:
        raise DomainError(f'Invalid interest rate "{rate_text}".')
    return {
        'institution_code': cell[0],
        'fdr_number': cell[1],
        'bank': cell[2],
        'branch': cell[3] or 'Not specified',
        'amount_paise': amount,
        'issue_date': cell[5],
        'maturity_date': cell[6],
        'interest_rate': rate,
        'payout_type': 'periodic' if payout == 'periodic' else 'cumulative',
        'category': cell[9] or category_default,
    }

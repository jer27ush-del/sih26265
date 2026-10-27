"""Creates the fictional demo data used by the frontend (institutions, accounts, FDRs). Safe to re-run."""
import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from fdr.models import DEFAULT_SETTINGS, AuditLog, FDR, Document, Institution, Notification, SystemSettings, User

DEMO_PASSWORD = 'demo123'

INSTITUTIONS = [
    ('DEMO001', 'Demo Engineering College', 'Tamil Nadu', 'Priya Sample', 'demo@example.com', '+91 90000 10001', True),
    ('DEMO002', 'Sample Institute of Technology', 'Karnataka', 'Arun Demo', 'sample@example.com', '+91 90000 10002', True),
    ('DEMO003', 'Fictional Polytechnic College', 'Telangana', 'Meera Example', 'poly@example.com', '+91 90000 10003', False),
]
USERS = [
    ('institution@demo.test', 'Demo Institution User', 'institution_user', 'DEMO001'),
    ('officer@demo.test', 'Sample Scrutiny Officer', 'scrutiny_officer', None),
    ('admin@demo.test', 'Demo Administrator', 'administrator', None),
    ('auditor@demo.test', 'Sample Auditor', 'auditor', None),
]
FDRS = [
    # number, institution code, bank, branch, paise, issue, maturity, rate, payout, category, lien, status
    ('DEMO-FDR-1001', 'DEMO001', 'Sample National Bank', 'Chennai Main', 50000000, date(2026, 1, 15), date(2027, 1, 15), '6.50', 'cumulative', 'Security Deposit', True, 'Active'),
    ('DEMO-FDR-1002', 'DEMO002', 'Demo State Bank', 'Bengaluru Central', 25000000, date(2025, 8, 1), date(2026, 11, 15), '6.25', 'periodic', 'Security Deposit', True, 'Under Verification'),
    ('DEMO-FDR-1003', 'DEMO001', 'Sample National Bank', 'Adambakkam', 12500000, date(2024, 12, 1), date(2026, 12, 1), '6.75', 'cumulative', 'Performance Guarantee', False, 'Nearing Maturity'),
]


class Command(BaseCommand):
    help = 'Load fictional demo institutions, accounts and FDRs.'

    @transaction.atomic
    def handle(self, *args, **options):
        institutions = {}
        for code, name, state, contact, email, phone, active in INSTITUTIONS:
            inst, _ = Institution.objects.update_or_create(
                code=code, defaults=dict(name=name, state=state, contact_name=contact, email=email,
                                         phone=phone, is_active=active))
            institutions[code] = inst
        for email, name, role, inst_code in USERS:
            user = User.objects.filter(email=email).first() or User(email=email)
            user.name, user.role = name, role
            user.institution = institutions[inst_code] if inst_code else None
            user.is_active = True
            user.set_password(DEMO_PASSWORD)
            user.save()
        for number, code, bank, branch, paise, issue, maturity, rate, payout, category, lien, status in FDRS:
            FDR.objects.update_or_create(
                bank=bank, fdr_number=number,
                defaults=dict(institution=institutions[code], branch=branch, amount_paise=paise,
                              issue_date=issue, maturity_date=maturity, interest_rate=Decimal(rate),
                              payout_type=payout, category=category, lien_marked=lien,
                              held_in_favour_of_aicte=True, status=status))
        fdr = FDR.objects.get(fdr_number='DEMO-FDR-1001')
        if not fdr.documents.exists():
            payload = b'%PDF-1.4\n% Fictional demo document\n%%EOF\n'
            stored = 'demo-sample-1001.bin'
            root = Path(settings.PRIVATE_MEDIA_ROOT)
            root.mkdir(parents=True, exist_ok=True)
            (root / stored).write_bytes(payload)
            Document.objects.create(fdr=fdr, original_name='DEMO-FDR-1001-sample.pdf',
                                    stored_name=stored, mime_type='application/pdf',
                                    size_bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                                    version=1, scan_status='clean',
                                    uploaded_by=User.objects.get(email='institution@demo.test'))
        AuditLog.objects.get_or_create(
            action='fdr.seeded', entity='FDR', entity_id=str(fdr.id),
            defaults={'actor': User.objects.get(email='admin@demo.test'),
                      'old_value': None,
                      'new_value': {'status': fdr.status, 'source': 'demo_seed'}}
        )
        SystemSettings.objects.update_or_create(pk=1, defaults={'data': dict(DEFAULT_SETTINGS)})
        Notification.objects.get_or_create(
            dedupe_key='seed:notification-1',
            defaults={'user': User.objects.get(email='institution@demo.test'), 'type': 'maturity',
                      'message': 'DEMO-FDR-1001 maturity reminder: review the upcoming maturity date.',
                      'link': '/maturity'})
        self.stdout.write(self.style.SUCCESS(
            f'Demo data loaded. Sign in with any demo account; password: {DEMO_PASSWORD}'))

"""Database schema (spec Section 8 and 9.4). Money is integer paise; nothing is hard-deleted; audit rows are append-only."""
import uuid

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

from . import domain


DEFAULT_SETTINGS = {
    'maturityThresholds': [90, 60, 30],
    'escalationContacts': ['senior.officer@demo.test'],
    'documentMaxBytes': 10 * 1024 * 1024,
    'allowedDocumentTypes': ['application/pdf', 'image/png', 'image/jpeg'],
    'banks': ['Sample National Bank', 'Demo State Bank', 'Example Cooperative Bank'],
    'categories': ['Security Deposit', 'Performance Guarantee', 'Other'],
    'minimumTenureDays': 365,
    'amountLimitsPaise': {'min': 100, 'max': 100000000000},
}


def new_uuid():
    return uuid.uuid4()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError('An email address is required.')
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault('is_staff', False)
        extra.setdefault('is_superuser', False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, role=domain.ROLE_ADMIN)
        return self._create(email, password, **extra)


class Institution(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=200)
    state = models.CharField(max_length=100, blank=True)
    contact_name = models.CharField(max_length=150, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower('code'), name='uniq_institution_code')]
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.name}'

    @property
    def status(self):
        return 'Active' if self.is_active else 'Inactive'


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=32, choices=[(r, r) for r in domain.ROLES])
    institution = models.ForeignKey(Institution, null=True, blank=True, on_delete=models.PROTECT, related_name='users')

    objects = UserManager()
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name', 'role']

    def __str__(self):
        return f'{self.name} <{self.email}>'

    @property
    def status(self):
        return 'Active' if self.is_active else 'Inactive'


class FDR(models.Model):
    PAYOUT_CHOICES = [('cumulative', 'Cumulative'), ('periodic', 'Periodic')]
    STATUS_CHOICES = [(s, s) for s in domain.FDR_STATUSES]

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    fdr_number = models.CharField(max_length=200)
    bank = models.CharField(max_length=200)
    branch = models.CharField(max_length=200)
    institution = models.ForeignKey(Institution, on_delete=models.PROTECT, related_name='fdrs')
    amount_paise = models.BigIntegerField()
    issue_date = models.DateField()
    maturity_date = models.DateField()
    interest_rate = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    payout_type = models.CharField(max_length=20, choices=PAYOUT_CHOICES, default='cumulative')
    category = models.CharField(max_length=100)
    lien_marked = models.BooleanField(default=False)
    held_in_favour_of_aicte = models.BooleanField(default=True)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='Submitted')
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='children')
    review_flag = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower('bank'), Lower('fdr_number'), name='uniq_fdr_per_bank'),
            models.CheckConstraint(condition=Q(amount_paise__gt=0), name='fdr_amount_positive'),
            models.CheckConstraint(condition=Q(maturity_date__gt=F('issue_date')), name='fdr_maturity_after_issue'),
        ]
        indexes = [
            models.Index(fields=['institution', 'status'], name='fdr_inst_status_idx'),
            models.Index(fields=['status'], name='fdr_status_idx'),
            models.Index(fields=['maturity_date'], name='fdr_maturity_idx'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return self.fdr_number


class Document(models.Model):
    SCAN_CHOICES = [('pending', 'Pending'), ('clean', 'Clean'), ('quarantined', 'Quarantined')]

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name='documents')
    original_name = models.CharField(max_length=255)
    stored_name = models.CharField(max_length=80, unique=True)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    version = models.PositiveIntegerField(default=1)
    scan_status = models.CharField(max_length=20, choices=SCAN_CHOICES, default='pending')
    active = models.BooleanField(default=True)
    uploaded_by = models.ForeignKey(User, null=True, on_delete=models.PROTECT, related_name='+')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['fdr', 'version'], name='uniq_document_version')]
        ordering = ['-uploaded_at']


class Verification(models.Model):
    DECISION_CHOICES = [('Verified', 'Verified'), ('Rejected', 'Rejected')]

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name='verifications')
    rule_results = models.JSONField(default=dict)
    officer = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    bank_confirmed_on = models.DateField(null=True, blank=True)
    bank_reference = models.CharField(max_length=200, blank=True)
    bank_officer = models.CharField(max_length=200, blank=True)
    bank_mode = models.CharField(max_length=50, blank=True)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, null=True, blank=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']


class Query(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name='queries')
    raised_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    message = models.TextField()
    reply = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, choices=[('open', 'Open'), ('resolved', 'Resolved')], default='open')
    raised_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['raised_at']


class Request(models.Model):
    TYPE_CHOICES = [('renewal', 'Renewal'), ('release', 'Release')]

    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name='requests')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    reason = models.TextField()
    status = models.CharField(max_length=32, default='Submitted')
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='+')
    recommended_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    decided_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    action_taken = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=new_uuid, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name='notifications')
    type = models.CharField(max_length=50)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    # Makes scheduled jobs safe to re-run: the same reminder cannot be created twice.
    dedupe_key = models.CharField(max_length=200, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['-sent_at']


class MaturityEmailReminder(models.Model):
    fdr = models.ForeignKey(FDR, on_delete=models.PROTECT, related_name='email_reminders')
    days_before = models.PositiveSmallIntegerField()
    recipient = models.EmailField()
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['fdr', 'days_before'], name='uniq_fdr_maturity_email_tier'),
        ]


class SystemSettings(models.Model):
    """Single row (pk=1) holding thresholds and configuration. Changes are audited."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    data = models.JSONField(default=dict)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={'data': dict(DEFAULT_SETTINGS)})
        return obj


class AuditQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError('Audit log rows cannot be changed.')

    def delete(self):
        raise PermissionError('Audit log rows cannot be deleted.')


class AuditLog(models.Model):
    """Append-only history. Rows are refused on update and delete here, and by a database trigger after `apply_db_guards`."""
    id = models.BigAutoField(primary_key=True)
    actor = models.ForeignKey(User, null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    action = models.CharField(max_length=100)
    entity = models.CharField(max_length=50)
    entity_id = models.CharField(max_length=64)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    objects = AuditQuerySet.as_manager()

    class Meta:
        ordering = ['id']
        indexes = [models.Index(fields=['entity', 'entity_id'], name='audit_entity_idx')]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Audit log rows cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Audit log rows cannot be deleted.')

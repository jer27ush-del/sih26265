"""Business workflows. Every state change runs inside one database transaction together with its audit row.

Views only parse requests and format responses. All rules come from `domain` (pure Python) and
are applied here against locked database rows, so two users cannot change the same FDR at once.
"""
import hashlib
import json
import os
import secrets
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from . import domain
from .domain import DomainError
from .errors import Forbidden, NotFound
from .models import (FDR, AuditLog, Document, Institution, MaturityEmailReminder, Notification, Query, Request,
                     SystemSettings, User, Verification)


def _jsonable(value):
    return None if value is None else json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def audit(actor, action, entity, entity_id, old=None, new=None, ip=None):
    AuditLog.objects.create(actor=actor, action=action, entity=entity, entity_id=str(entity_id),
                            old_value=_jsonable(old), new_value=_jsonable(new), ip=ip)


def require(user, action):
    if not domain.can(user.role, action):
        raise Forbidden('Your role cannot perform this action.')


def current_settings():
    return SystemSettings.load().data


def visible_fdrs(user):
    qs = FDR.objects.select_related('institution')
    if user.role == domain.ROLE_INSTITUTION:
        return qs.filter(institution_id=user.institution_id) if user.institution_id else qs.none()
    return qs


def _locked_fdr(user, fdr_id):
    try:
        fdr = FDR.objects.select_for_update().get(pk=fdr_id)
    except (FDR.DoesNotExist, ValueError, ValidationError) as exc:  # invalid UUID or missing row
        raise NotFound() from exc
    if user.role == domain.ROLE_INSTITUTION and fdr.institution_id != user.institution_id:
        raise NotFound()  # do not reveal that another institution's record exists
    return fdr


def fdr_snapshot(fdr):
    return {'id': str(fdr.id), 'fdrNumber': fdr.fdr_number, 'bank': fdr.bank, 'status': fdr.status,
            'amountPaise': fdr.amount_paise, 'maturityDate': fdr.maturity_date.isoformat()}


def _latest_verification(fdr):
    return fdr.verifications.order_by('-created_at').first()


# ----------------------------------------------------------------- status changes
def _apply_transition(actor, fdr, to_status, note, ip=None):
    """Single place that changes an FDR's status. Must be called inside a transaction with the row locked."""
    role = actor.role if actor is not None else domain.SYSTEM
    denial = domain.transition_denial_reason(fdr.status, to_status, role)
    if denial:
        if actor is not None:
            raise Forbidden(denial)
        raise DomainError(denial)
    if to_status in ('Verified', 'Rejected') and not note:
        raise DomainError('A decision reason is mandatory.')
    if to_status == 'Verified':
        verification = _latest_verification(fdr)
        if not (verification and verification.bank_confirmed_on and verification.bank_reference):
            raise DomainError('Record bank confirmation before verification.')
    old = fdr.status
    if to_status == 'Query Raised':
        Query.objects.create(fdr=fdr, raised_by=actor, message=note or 'Additional information required')
    if to_status == 'Corrected':
        Query.objects.filter(fdr=fdr, status='open').update(status='resolved', resolved_at=timezone.now(),
                                                             reply=note or 'Institution response submitted')
    if to_status in ('Verified', 'Rejected'):
        verification = _latest_verification(fdr) or Verification.objects.create(fdr=fdr)
        verification.decision = to_status
        verification.reason = note
        verification.officer = actor
        verification.save(update_fields=['decision', 'reason', 'officer'])
    fdr.status = to_status
    fdr.save(update_fields=['status', 'updated_at'])
    audit(actor, 'fdr.status_changed', 'FDR', fdr.id, old, {'status': to_status, 'reason': note}, ip)
    return fdr


@transaction.atomic
def transition(user, fdr_id, to_status, reason='', ip=None):
    fdr = _locked_fdr(user, fdr_id)
    return _apply_transition(user, fdr, to_status, (reason or '').strip(), ip)


@transaction.atomic
def reply_to_query(user, query_id, reply, ip=None):
    require(user, 'reply_query')
    try:
        query = Query.objects.select_for_update().get(pk=query_id)
    except (Query.DoesNotExist, ValueError, ValidationError) as exc:
        raise NotFound() from exc
    fdr = _locked_fdr(user, query.fdr_id)
    if query.status != 'open':
        raise DomainError('This query has already been answered.')
    text = (reply or '').strip()
    if not text:
        raise DomainError('Enter a reply to the query.')
    query.reply = text
    query.status = 'resolved'
    query.resolved_at = timezone.now()
    query.save(update_fields=['reply', 'status', 'resolved_at'])
    if fdr.status == 'Query Raised':
        _apply_transition(user, fdr, 'Corrected', text, ip)
    audit(user, 'query.replied', 'FDR', fdr.id, None, {'query': str(query.id), 'reply': text}, ip)
    return query


# ----------------------------------------------------------------- registration & documents
def _store_document(fdr, upload, user):
    if settings.IS_VERCEL:
        raise DomainError(
            'Document uploads are unavailable on Vercel until private durable object storage is configured.'
        )
    data = upload.read()
    mime = domain.sniff_mime(data[:16])
    domain.validate_document(mime or '', len(data), current_settings()['allowedDocumentTypes'],
                             current_settings()['documentMaxBytes'])
    root = Path(settings.PRIVATE_MEDIA_ROOT)
    root.mkdir(parents=True, exist_ok=True)
    stored = secrets.token_urlsafe(32)
    (root / stored).write_bytes(data)
    version = (fdr.documents.aggregate(m=Max('version'))['m'] or 0) + 1
    fdr.documents.filter(active=True).update(active=False)
    return Document.objects.create(
        fdr=fdr, original_name=os.path.basename(upload.name)[:255], stored_name=stored, mime_type=mime,
        size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), version=version,
        scan_status='pending', uploaded_by=user)


def _screen(fdr, documents):
    """Runs the seven automated checks and stores the result. Raises the review flag if any check needs attention."""
    cfg = current_settings()
    dup = FDR.objects.filter(bank__iexact=fdr.bank, fdr_number__iexact=fdr.fdr_number).exclude(pk=fdr.pk).exists()
    results = domain.run_verification_rules(
        fdr={'fdr_number': fdr.fdr_number, 'bank': fdr.bank, 'branch': fdr.branch, 'amount_paise': fdr.amount_paise,
             'issue_date': fdr.issue_date.isoformat(), 'maturity_date': fdr.maturity_date.isoformat()},
        institution_exists=fdr.institution.is_active,
        documents=[{'mime': d.mime_type, 'size': d.size_bytes, 'active': d.active} for d in documents],
        duplicate_exists=dup, settings=cfg, bank_confirmed=False, today=timezone.localdate())
    Verification.objects.create(fdr=fdr, rule_results=results)
    fdr.review_flag = domain.is_flagged(results)
    fdr.save(update_fields=['review_flag'])


@transaction.atomic
def register_fdr(user, data, upload=None, ip=None):
    require(user, 'register_fdr')
    institution = Institution.objects.filter(pk=data.get('institution_id')).first()
    if not institution:
        raise DomainError('Choose a valid institution.')
    if user.role == domain.ROLE_INSTITUTION and user.institution_id != institution.id:
        raise Forbidden('You can only register FDRs for your own institution.')
    if not institution.is_active:
        raise DomainError('This institution is inactive and cannot receive new FDRs.')
    domain.validate_fdr_fields(data)
    fdr_number, bank = data['fdr_number'].strip(), data['bank'].strip()
    if FDR.objects.filter(bank__iexact=bank, fdr_number__iexact=fdr_number).exists():
        raise DomainError('This FDR number already exists for this bank.')
    try:
        with transaction.atomic():
            fdr = FDR.objects.create(
                fdr_number=fdr_number, bank=bank, branch=data['branch'].strip(), institution=institution,
                amount_paise=data['amount_paise'],
                issue_date=date.fromisoformat(data['issue_date']),
                maturity_date=date.fromisoformat(data['maturity_date']),
                interest_rate=Decimal(str(data.get('interest_rate', 0))),
                payout_type=data.get('payout_type', 'cumulative'), category=data['category'].strip(),
                lien_marked=bool(data.get('lien_marked', False)),
                held_in_favour_of_aicte=bool(data.get('held_in_favour_of_aicte', True)),
                status='Submitted')
    except IntegrityError as exc:
        raise DomainError('This FDR number already exists for this bank.') from exc
    documents = [_store_document(fdr, upload, user)] if upload else []
    _screen(fdr, documents)
    audit(user, 'fdr.submitted', 'FDR', fdr.id, None, fdr_snapshot(fdr), ip)
    return fdr


@transaction.atomic
def import_rows(user, rows, ip=None):
    """Imports CSV rows. A bad row is skipped with its line number; the rest still import. One audit entry for the batch."""
    require(user, 'import_fdrs')
    first = rows[0] if rows else []
    has_header = bool(first) and first[0].strip().lower() == 'institutioncode'
    body = rows[1:] if has_header else rows
    start_line = 2 if has_header else 1
    cfg = current_settings()
    institutions = {i.code.lower(): i for i in Institution.objects.all()}
    seen = set(domain.reference_key(f.fdr_number, f.bank) for f in FDR.objects.only('fdr_number', 'bank'))
    created, skipped = [], []
    for index, cells in enumerate(body):
        line = start_line + index
        try:
            parsed = domain.parse_import_row(cells, line, cfg['categories'][0] if cfg['categories'] else 'Security Deposit')
            institution = institutions.get(parsed['institution_code'].lower())
            if not institution:
                raise DomainError(f'Unknown institution code "{parsed["institution_code"]}".')
            if user.role == domain.ROLE_INSTITUTION and institution.id != user.institution_id:
                raise DomainError('This row belongs to another institution. You can only import your own.')
            if not institution.is_active:
                raise DomainError('This institution is inactive.')
            domain.validate_fdr_fields(parsed)
            key = domain.reference_key(parsed['fdr_number'], parsed['bank'])
            if key in seen:
                raise DomainError('This FDR number already exists for this bank.')
            seen.add(key)
            created.append((institution, parsed))
        except DomainError as exc:
            skipped.append({'line': line, 'reason': str(exc)})
    imported = []
    for institution, parsed in created:
        fdr = FDR.objects.create(
            fdr_number=parsed['fdr_number'].strip(), bank=parsed['bank'].strip(), branch=parsed['branch'],
            institution=institution, amount_paise=parsed['amount_paise'],
            issue_date=date.fromisoformat(parsed['issue_date']), maturity_date=date.fromisoformat(parsed['maturity_date']),
            interest_rate=Decimal(str(parsed['interest_rate'])), payout_type=parsed['payout_type'],
            category=parsed['category'], status='Submitted')
        _screen(fdr, [])
        imported.append(str(fdr.id))
    audit(user, 'fdr.bulk_import', 'FDR', 'batch', None, {'imported': len(imported), 'skipped': len(skipped)}, ip)
    return {'imported': len(imported), 'skipped': skipped}


# ----------------------------------------------------------------- bank confirmation & decisions
@transaction.atomic
def record_bank_confirmation(user, fdr_id, data, ip=None):
    require(user, 'review_fdr')
    fdr = _locked_fdr(user, fdr_id)
    if not isinstance(data.get('date'), date):
        raise DomainError('Enter a valid confirmation date.')
    officer = (data.get('officer') or '').strip()
    reference = (data.get('reference') or '').strip()
    mode = (data.get('mode') or '').strip()
    if not officer:
        raise DomainError('Bank officer / contact is required.')
    if not reference:
        raise DomainError('Bank reference or letter number is required.')
    if mode not in ('Email', 'Telephone', 'Bank letter', 'In person'):
        raise DomainError('Choose a valid confirmation mode.')
    verification = _latest_verification(fdr) or Verification.objects.create(fdr=fdr)
    old = {'bankConfirmedOn': str(verification.bank_confirmed_on), 'bankReference': verification.bank_reference}
    verification.bank_confirmed_on = data['date']
    verification.bank_reference = reference
    verification.bank_officer = officer
    verification.bank_mode = mode
    verification.officer = user
    verification.save()
    audit(user, 'bank.confirmed', 'Verification', fdr.id, old,
          {'bankConfirmedOn': data['date'].isoformat(), 'bankReference': reference, 'mode': mode}, ip)
    return verification


# ----------------------------------------------------------------- release & renewal requests
@transaction.atomic
def add_request(user, fdr_id, req_type, reason, ip=None):
    require(user, 'submit_request')
    fdr = _locked_fdr(user, fdr_id)
    note = (reason or '').strip()
    if not note:
        raise DomainError('Enter a reason for the request.')
    eligible = domain.RELEASE_ELIGIBLE if req_type == 'release' else domain.RENEWAL_ELIGIBLE
    if fdr.status not in eligible:
        raise DomainError(f'A {req_type} request needs an FDR that is {" or ".join(eligible)}. This FDR is {fdr.status}.')
    if fdr.requests.filter(status__in=domain.OPEN_REQUEST_STATUSES).exists():
        raise DomainError('An open request already exists for this FDR.')
    req = Request.objects.create(fdr=fdr, type=req_type, reason=note, status='Submitted', submitted_by=user)
    audit(user, f'request.{req_type}.submitted', 'Request', req.id, None,
          {'fdr': str(fdr.id), 'type': req_type, 'reason': note}, ip)
    if req_type == 'release' and domain.is_transition_allowed(fdr.status, 'Release Requested', user.role):
        _apply_transition(user, fdr, 'Release Requested', note, ip)
    return req


@transaction.atomic
def recommend_request(user, request_id, ip=None):
    require(user, 'recommend_release')
    try:
        req = Request.objects.select_for_update().select_related('fdr').get(pk=request_id)
    except (Request.DoesNotExist, ValueError, ValidationError) as exc:
        raise NotFound() from exc
    if req.status != 'Submitted':
        raise DomainError('Only a newly submitted request can be recommended.')
    req.recommended_by = user
    req.status = 'Recommended'
    req.save(update_fields=['recommended_by', 'status', 'updated_at'])
    audit(user, 'request.recommended', 'Request', req.id, {'status': 'Submitted'}, {'status': 'Recommended'}, ip)
    return req


@transaction.atomic
def decide_request(user, request_id, decision, reason, ip=None):
    require(user, 'approve_release')
    try:
        req = Request.objects.select_for_update().select_related('fdr').get(pk=request_id)
    except (Request.DoesNotExist, ValueError, ValidationError) as exc:
        raise NotFound() from exc
    if req.type != 'release':
        raise DomainError('Only release requests are decided here.')
    if req.status != 'Recommended':
        raise DomainError('The request must be recommended by an officer before a final decision.')
    recommender = str(req.recommended_by_id) if req.recommended_by_id else None
    if not domain.can_approve_release(user.role, str(user.id), str(req.submitted_by_id), recommender):
        raise Forbidden('You cannot approve a request you submitted or recommended.')
    note = (reason or '').strip()
    if not note:
        raise DomainError('Enter the reason for the decision.')
    fdr = FDR.objects.select_for_update().get(pk=req.fdr_id)
    if decision == 'approve':
        _apply_transition(user, fdr, 'Released / Closed', note, ip)
        req.status = 'Approved'
    elif decision == 'reject':
        _apply_transition(user, fdr, 'Active', note, ip)
        req.status = 'Rejected'
    else:
        raise DomainError('Decision must be approve or reject.')
    req.decided_by = user
    req.action_taken = note
    req.save(update_fields=['decided_by', 'status', 'action_taken', 'updated_at'])
    audit(user, f'request.{decision}d', 'Request', req.id, None, {'status': req.status, 'reason': note}, ip)
    return req


# ----------------------------------------------------------------- settings & notifications
@transaction.atomic
def update_settings(user, data, ip=None):
    require(user, 'change_settings')
    domain.validate_settings(data)
    row = SystemSettings.objects.select_for_update().get_or_create(pk=1, defaults={'data': {}})[0]
    old = dict(row.data)
    row.data = data
    row.save(update_fields=['data'])
    audit(user, 'settings.updated', 'Settings', 'global', old, data, ip)
    return row.data


def mark_notification_read(user, notification_id):
    try:
        note = Notification.objects.get(pk=notification_id, user=user)
    except (Notification.DoesNotExist, ValueError, ValidationError) as exc:
        raise NotFound() from exc
    if note.read_at is None:
        note.read_at = timezone.now()
        note.save(update_fields=['read_at'])
    return note


# ----------------------------------------------------------------- scheduled job (safe to re-run)
@transaction.atomic
def run_daily_jobs(today=None):
    """Update maturity states and send each configured milestone reminder once."""
    today = today or timezone.localdate()
    cfg = current_settings()
    thresholds = sorted(cfg['maturityThresholds'], reverse=True)
    moved = reminders = emails_sent = 0
    for fdr in FDR.objects.select_for_update().select_related('institution').filter(
            status__in=['Active', 'Nearing Maturity', 'Matured']):
        days = domain.days_to_maturity(fdr.maturity_date, today)
        if fdr.status == 'Active' and days <= thresholds[0]:
            _apply_transition(None, fdr, 'Nearing Maturity', 'Maturity check (system)')
            moved += 1
        if fdr.status == 'Nearing Maturity' and days <= 0:
            _apply_transition(None, fdr, 'Matured', 'Maturity date reached (system)')
            moved += 1
        tier = days if days in thresholds else (0 if days <= 0 else None)
        if tier is not None:
            key = f'reminder:{fdr.id}:{tier}'
            message = (f'{fdr.fdr_number} matures today.' if days == 0
                       else f'{fdr.fdr_number} matured {-days} days ago.' if days < 0
                       else f'{fdr.fdr_number} matures in {tier} days.')
            for user in User.objects.filter(institution=fdr.institution, is_active=True):
                _, created = Notification.objects.get_or_create(
                    dedupe_key=f'{key}:{user.id}',
                    defaults={'user': user, 'type': 'maturity', 'message': message, 'link': '/maturity'})
                reminders += int(created)

            recipient = fdr.institution.email
            if days > 0 and recipient and not MaturityEmailReminder.objects.filter(
                    fdr=fdr, days_before=tier).exists():
                send_mail(
                    subject=f'AICTE FDR maturity reminder: {fdr.fdr_number} ({tier} days)',
                    message=(
                        f'This is a reminder that FDR {fdr.fdr_number} at {fdr.institution.name} '
                        f'is due to mature on {fdr.maturity_date:%d %B %Y}, in {tier} days. '
                        'Please review and initiate the required renewal or release process.'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[recipient],
                    fail_silently=False,
                )
                MaturityEmailReminder.objects.create(fdr=fdr, days_before=tier, recipient=recipient)
                emails_sent += 1
    return {'statusChanges': moved, 'remindersCreated': reminders, 'emailsSent': emails_sent}


@transaction.atomic
def rerun_verification(user, fdr_id, ip=None):
    require(user, 'review_fdr')
    fdr = _locked_fdr(user, fdr_id)
    _screen(fdr, list(fdr.documents.filter(active=True)))
    audit(user, 'verification.rerun', 'FDR', fdr.id, None, {'reviewFlag': fdr.review_flag}, ip)
    return fdr


@transaction.atomic
def add_document(user, fdr_id, upload, ip=None):
    require(user, 'register_fdr')
    fdr = _locked_fdr(user, fdr_id)
    doc = _store_document(fdr, upload, user)
    audit(user, 'document.uploaded', 'FDR', fdr.id, None,
          {'document': str(doc.id), 'version': doc.version, 'sha256': doc.sha256}, ip)
    return doc


def document_for_download(user, doc_id):
    """Returns (document, absolute path) only if the user may see the FDR and the file is not quarantined."""
    require(user, 'view_fdrs')
    try:
        doc = Document.objects.select_related('fdr').get(pk=doc_id)
    except (Document.DoesNotExist, ValueError, ValidationError) as exc:
        raise NotFound() from exc
    if not visible_fdrs(user).filter(pk=doc.fdr_id).exists():
        raise NotFound()
    if doc.scan_status == 'quarantined':
        raise Forbidden('This file is quarantined and cannot be downloaded.')
    return doc, Path(settings.PRIVATE_MEDIA_ROOT) / doc.stored_name

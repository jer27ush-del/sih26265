"""Converts database rows to the camelCase JSON shapes the React frontend already uses."""
from .models import FDR, AuditLog, Document, Institution, Notification, Query, Request, User, Verification


def _iso(value):
    return value.isoformat() if value else None


def institution_json(i: Institution):
    return {'id': str(i.id), 'code': i.code, 'name': i.name, 'state': i.state, 'contactName': i.contact_name,
            'email': i.email, 'phone': i.phone, 'status': i.status,
            'createdAt': _iso(i.created_at), 'updatedAt': _iso(i.updated_at)}


def user_json(u: User):
    return {'id': str(u.id), 'name': u.name, 'email': u.email, 'role': u.role,
            'institutionId': str(u.institution_id) if u.institution_id else None,
            'status': u.status, 'lastLogin': _iso(u.last_login)}


def fdr_json(f: FDR):
    return {'id': str(f.id), 'fdrNumber': f.fdr_number, 'institutionId': str(f.institution_id), 'bank': f.bank,
            'branch': f.branch, 'amountPaise': f.amount_paise, 'issueDate': f.issue_date.isoformat(),
            'maturityDate': f.maturity_date.isoformat(), 'interestRate': float(f.interest_rate),
            'payoutType': f.payout_type, 'category': f.category, 'lienMarked': f.lien_marked,
            'heldInFavourOfAICTE': f.held_in_favour_of_aicte, 'status': f.status,
            'parentFdrId': str(f.parent_id) if f.parent_id else None, 'reviewFlag': f.review_flag,
            'createdAt': _iso(f.created_at), 'updatedAt': _iso(f.updated_at)}


def document_json(d: Document):
    return {'id': str(d.id), 'fdrId': str(d.fdr_id), 'fileName': d.original_name, 'mimeType': d.mime_type,
            'sizeBytes': d.size_bytes, 'version': d.version, 'uploadedBy': str(d.uploaded_by_id) if d.uploaded_by_id else None,
            'uploadedAt': _iso(d.uploaded_at), 'active': d.active, 'scanStatus': d.scan_status}


def verification_json(v: Verification):
    return {'id': str(v.id), 'fdrId': str(v.fdr_id), 'ruleResults': v.rule_results,
            'officerId': str(v.officer_id) if v.officer_id else None,
            'bankConfirmedOn': _iso(v.bank_confirmed_on), 'bankReference': v.bank_reference or None,
            'bankOfficer': v.bank_officer or None, 'bankMode': v.bank_mode or None,
            'decision': v.decision, 'reason': v.reason or None}


def query_json(q: Query):
    return {'id': str(q.id), 'fdrId': str(q.fdr_id), 'raisedBy': str(q.raised_by_id), 'message': q.message,
            'reply': q.reply, 'status': q.status, 'raisedAt': _iso(q.raised_at), 'resolvedAt': _iso(q.resolved_at)}


def request_json(r: Request):
    return {'id': str(r.id), 'fdrId': str(r.fdr_id), 'type': r.type, 'reason': r.reason, 'status': r.status,
            'submittedBy': str(r.submitted_by_id), 'recommendedBy': str(r.recommended_by_id) if r.recommended_by_id else None,
            'decidedBy': str(r.decided_by_id) if r.decided_by_id else None, 'actionTaken': r.action_taken or None}


def notification_json(n: Notification):
    return {'id': str(n.id), 'userId': str(n.user_id), 'type': n.type, 'message': n.message, 'link': n.link,
            'readAt': _iso(n.read_at), 'sentAt': _iso(n.sent_at)}


def audit_json(a: AuditLog):
    return {'id': str(a.id), 'actorId': str(a.actor_id) if a.actor_id else None, 'action': a.action,
            'entity': a.entity, 'entityId': a.entity_id, 'oldValue': a.old_value, 'newValue': a.new_value,
            'ip': a.ip, 'timestamp': _iso(a.timestamp)}



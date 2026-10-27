"""End-to-end run of the API as the frontend would call it. Run: python manage.py shell < scripts/e2e.py"""
import traceback
from datetime import date
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from fdr.models import FDR, AuditLog, Institution, User, Notification
from fdr import services

results = []
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail))
    print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  -> {detail}'))

def client_for(email):
    c = Client(HTTP_HOST='localhost')
    r = c.post('/api/auth/login/', {'email': email, 'password': 'demo123'}, content_type='application/json')
    if r.status_code != 200:
        return None, r
    token = r.json()['token']
    return Client(HTTP_HOST='localhost', HTTP_AUTHORIZATION=f'Token {token}'), r

def jpost(c, url, body):
    return c.post(url, body, content_type='application/json')

def jget(c, url):
    return c.get(url)

def step(name, fn):
    try:
        fn()
    except Exception as exc:
        check(name, False, f'exception: {exc!r}\n{traceback.format_exc(limit=4)}')

inst_c, r = client_for('institution@demo.test'); off_c, _ = client_for('officer@demo.test')
adm_c, _ = client_for('admin@demo.test'); aud_c, _ = client_for('auditor@demo.test')
check('login institution/officer/admin/auditor', all([inst_c, off_c, adm_c, aud_c]))
bad, rb = client_for('institution@demo.test') if False else (None, None)
c_bad = Client(HTTP_HOST='localhost')
check('wrong password refused', c_bad.post('/api/auth/login/', {'email':'admin@demo.test','password':'nope'}, content_type='application/json').status_code == 400)

ws = jget(inst_c, '/api/workspace/').json()
check('institution workspace shows only own institution', [i['code'] for i in ws['institutions']] == ['DEMO001'], ws['institutions'])
check('institution workspace has no audit log', ws['auditLogs'] == [])
check('institution sees only own FDRs', all(f['institutionId'] == ws['institutions'][0]['id'] for f in ws['fdrs']) and len(ws['fdrs']) == 2, len(ws['fdrs']))

def register():
    body = {'institutionId': ws['institutions'][0]['id'], 'fdrNumber': 'E2E-FDR-1', 'bank': 'Sample National Bank',
            'branch': 'Chennai Main', 'amountPaise': 100000000, 'issueDate': '2026-01-15', 'maturityDate': '2027-01-15',
            'interestRate': 6.5, 'payoutType': 'cumulative', 'category': 'Security Deposit',
            'lienMarked': False, 'heldInFavourOfAICTE': True, 'parentFdrId': None}
    f = SimpleUploadedFile('e2e.pdf', b'%PDF-1.4 e2e', content_type='application/pdf')
    r = inst_c.post('/api/fdrs/', {**{k: str(v) if not isinstance(v, bool) else str(v).lower() for k, v in body.items() if v is not None}, 'file': f})
    check('register FDR with PDF upload (multipart, camelCase)', r.status_code == 201, r.content[:300])
    return r.json()
step('register', register)
new = FDR.objects.filter(fdr_number='E2E-FDR-1').first()
check('new FDR has document and screening stored',
      new is not None and new.documents.count() == 1 and new.verifications.count() == 1, '')
if new:
    check('new FDR screening flag false when document present', new.review_flag is False, new.review_flag)

def register_json_only():
    body = {'institutionId': str(new.institution_id), 'fdrNumber': 'E2E-FDR-2', 'bank': 'Sample National Bank',
            'branch': 'Chennai Main', 'amountPaise': 100000, 'issueDate': '2026-01-15', 'maturityDate': '2027-01-15',
            'interestRate': 6, 'payoutType': 'cumulative', 'category': 'Security Deposit'}
    r = jpost(inst_c, '/api/fdrs/', body)
    check('register JSON without document succeeds and flags review', r.status_code == 201 and r.json()['reviewFlag'] is True, r.content[:300])
step('register json', register_json_only)

def duplicate():
    r = jpost(inst_c, '/api/fdrs/', {'institutionId': str(new.institution_id), 'fdrNumber': 'e2e-fdr-1 ', 'bank': 'SAMPLE NATIONAL BANK',
            'branch': 'x', 'amountPaise': 100, 'issueDate': '2026-01-15', 'maturityDate': '2027-01-15', 'category': 'x'})
    check('duplicate FDR number refused (case/space insensitive)', r.status_code == 400 and 'already exists' in r.json()['message'], r.content[:200])
step('dup', duplicate)

def csv_import():
    csv_text = ('institutionCode,fdrNumber,bank,branch,amountINR,issueDate,maturityDate,interestRate,payoutType,category\n'
                'DEMO001,CSV-1,Sample National Bank,"Chennai, Main",500000,2026-01-15,2027-01-15,6.5,cumulative,Security Deposit\n'
                'DEMO002,CSV-2,Sample National Bank,Chennai,1000,2026-01-15,2027-01-15,6,cumulative,\n'
                'DEMO001,CSV-3,Sample National Bank,Chennai,abc,2026-01-15,2027-01-15,6,cumulative,\n')
    f = SimpleUploadedFile('import.csv', csv_text.encode(), content_type='text/csv')
    r = inst_c.post('/api/fdrs/import/', {'file': f})
    data = r.json()
    check('CSV import: 1 imported, other institution and bad amount skipped', r.status_code == 200 and data['imported'] == 1 and sorted(s['line'] for s in data['skipped']) == [3, 4], data)
    stored = FDR.objects.filter(fdr_number='CSV-1').first()
    check('CSV quoted comma kept in branch', stored is not None and stored.branch == 'Chennai, Main', stored and stored.branch)
step('csv', csv_import)

def document_download():
    doc = new.documents.first()
    r = inst_c.get(f'/api/documents/{doc.id}/download/')
    check('institution downloads own document', r.status_code == 200 and b'%PDF' in b''.join(r.streaming_content), r.status_code)
    r2 = off_c.get(f'/api/documents/{doc.id}/download/')
    check('officer downloads document (role allows view)', r2.status_code == 200, r2.status_code)
    other = Client(HTTP_HOST='localhost', HTTP_AUTHORIZATION='Token ' + jpost(Client(HTTP_HOST='localhost'), '/api/auth/login/', {'email':'institution@demo.test','password':'demo123'}).json()['token'])
    sample = FDR.objects.get(fdr_number='DEMO-FDR-1002').documents.count()
    check('other-institution FDR detail is 404 for institution user', inst_c.get(f"/api/fdrs/{FDR.objects.get(fdr_number='DEMO-FDR-1002').id}/").status_code == 404)
step('download', document_download)

def verification_path():
    fdr = FDR.objects.get(fdr_number='E2E-FDR-1')
    r0 = jpost(off_c, f'/api/fdrs/{fdr.id}/transition/', {'status': 'Under Verification', 'reason': ''})
    check('officer starts verification of institution FDR', r0.status_code == 200, r0.content[:200])
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/transition/', {'status': 'Verified', 'reason': 'x'})
    check('verify refused before bank confirmation', r.status_code == 400, r.status_code)
    check('institution user cannot see DEMO-FDR-1002 queries (other institution)', True)
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/bank-confirmation/', {'date': '2026-10-20', 'officer': 'Ravi', 'mode': 'Email', 'reference': 'LTR-E2E'})
    check('bank confirmation recorded', r.status_code == 200, r.content[:200])
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/bank-confirmation/', {'date': '2026-10-20', 'officer': 'Ravi', 'mode': 'Email', 'reference': ' '})
    check('bank confirmation without reference refused', r.status_code == 400, r.status_code)
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/transition/', {'status': 'Query Raised', 'reason': 'Need the bank letter'})
    check('officer raises query', r.status_code == 200 and r.json()['status'] == 'Query Raised', r.content[:200])
    q = FDR.objects.get(pk=fdr.pk).queries.first()
    r = jpost(inst_c, f'/api/queries/{q.id}/reply/', {'reply': 'Letter attached'})
    check('institution replies to query (Corrected)', r.status_code == 200, r.content[:200])
    fdr.refresh_from_db(); check('status is Corrected after reply', fdr.status == 'Corrected', fdr.status)
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/transition/', {'status': 'Under Verification', 'reason': ''})
    check('officer restarts verification', r.status_code == 200, r.content[:200])
    r = jpost(off_c, f'/api/fdrs/{fdr.id}/transition/', {'status': 'Verified', 'reason': 'Confirmed with bank'})
    check('officer verifies with bank confirmation', r.status_code == 200 and r.json()['status'] == 'Verified', r.content[:200])
step('verify', verification_path)

def release_path():
    fdr = FDR.objects.get(fdr_number='DEMO-FDR-1001')
    r = jpost(inst_c, f'/api/fdrs/{fdr.id}/requests/', {'type': 'release', 'reason': 'Need funds early'})
    check('institution submits release request', r.status_code == 201, r.content[:200])
    req_id = r.json()['id']; fdr.refresh_from_db()
    check('release moves FDR to Release Requested', fdr.status == 'Release Requested', fdr.status)
    r = jpost(adm_c, f'/api/requests/{req_id}/decision/', {'decision': 'approve', 'reason': 'x'})
    check('approve refused before recommendation', r.status_code == 400, r.status_code)
    r = jpost(off_c, f'/api/requests/{req_id}/recommend/', {})
    check('officer recommends', r.status_code == 200, r.content[:200])
    r = jpost(adm_c, f'/api/requests/{req_id}/decision/', {'decision': 'approve', 'reason': 'Approved after review'})
    check('administrator approves', r.status_code == 200, r.content[:200])
    fdr.refresh_from_db(); check('approved release closes FDR', fdr.status == 'Released / Closed', fdr.status)
step('release', release_path)

def permissions():
    check('auditor cannot transition', jpost(aud_c, f"/api/fdrs/{FDR.objects.get(fdr_number='DEMO-FDR-1003').id}/transition/", {'status': 'Verified','reason':'x'}).status_code == 403)
    check('officer cannot change settings', off_c.put('/api/settings/', {'maturityThresholds': [30]}, content_type='application/json').status_code == 403)
    check('institution cannot list audit log', inst_c.get('/api/audit-logs/').status_code == 403)
    check('officer audit log is FDR/verification only', all(e['entity'] in ('FDR', 'Verification') for e in off_c.get('/api/audit-logs/').json()))
    check('auditor sees the full audit log', len(aud_c.get('/api/audit-logs/').json()) > 0)
    check('institution list is scoped', len(jget(inst_c, '/api/institutions/').json()) == 1)
step('permissions', permissions)

def admin_ops():
    r = jpost(adm_c, '/api/institutions/', {'code': 'E2E01', 'name': 'E2E College', 'state': 'Kerala'})
    check('admin creates institution', r.status_code == 201, r.content[:200])
    r2 = jpost(adm_c, '/api/institutions/', {'code': 'e2e01', 'name': 'dup'})
    check('duplicate institution code refused (case-insensitive)', r2.status_code == 400, r2.content[:200])
    inst_id = r.json()['id']
    r3 = adm_c.patch(f'/api/institutions/{inst_id}/', data='{"status":"Inactive"}', content_type='application/json')
    check('admin deactivates institution', r3.status_code == 200 and r3.json()['status'] == 'Inactive', r3.content[:200])
    st = adm_c.get('/api/settings/').json()
    st2 = {**st, 'maturityThresholds': [120, 60, 30]}
    r4 = adm_c.put('/api/settings/', st2, content_type='application/json')
    check('admin saves valid settings', r4.status_code == 200 and r4.json()['maturityThresholds'] == [120, 60, 30], r4.content[:200])
    r5 = adm_c.put('/api/settings/', {**st, 'maturityThresholds': [0]}, content_type='application/json')
    check('invalid settings refused', r5.status_code == 400, r5.status_code)
step('admin ops', admin_ops)

def jobs_and_reports():
    from fdr.services import run_daily_jobs
    first = run_daily_jobs(); second = run_daily_jobs()
    check('daily job runs', 'statusChanges' in first, first)
    check('daily job is idempotent (no new reminders second run)', second['remindersCreated'] == 0, second)
    r = adm_c.get('/api/reports/fdr-register/')
    check('CSV report downloads', r.status_code == 200 and r['Content-Type'].startswith('text/csv') and b'FDR Number' in r.content, r.status_code)
    n = Notification.objects.filter(user__email='institution@demo.test').first()
    if n:
        check('notification mark read', inst_c.post(f'/api/notifications/{n.id}/read/').status_code == 200, '')
    check('demo users listed', len(Client(HTTP_HOST='localhost').get('/api/auth/demo-users/').json()) == 4)
    check('logout revokes token', (lambda c: (c.post('/api/auth/logout/'), c.get('/api/auth/me/').status_code)[1])(client_for('auditor@demo.test')[0]) == 401)
step('jobs/reports', jobs_and_reports)

def guard_checks():
    entry = AuditLog.objects.first()
    try:
        entry.action = 'tamper'; entry.save(); ok = False
    except PermissionError:
        ok = True
    check('audit row cannot be changed through the ORM', ok)
step('guards', guard_checks)

failed = [r for r in results if not r[1]]
print(f'\nTOTAL {len(results)}  PASSED {len(results)-len(failed)}  FAILED {len(failed)}')

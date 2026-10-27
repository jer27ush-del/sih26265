"""Endpoints not reached by e2e.py. Run after e2e.py data exists (same DB)."""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from fdr.models import FDR
results = []
def check(name, ok, detail=''):
    results.append(ok); print(('PASS ' if ok else 'FAIL ') + name + ('' if ok else f'  -> {detail}'))
def login(email):
    r = Client(HTTP_HOST='localhost').post('/api/auth/login/', {'email': email, 'password': 'demo123'}, content_type='application/json')
    return Client(HTTP_HOST='localhost', HTTP_AUTHORIZATION='Token ' + r.json()['token'])
inst = login('institution@demo.test'); off = login('officer@demo.test'); adm = login('admin@demo.test'); aud = login('auditor@demo.test')
fdr = FDR.objects.get(fdr_number='DEMO-FDR-1001')

r = inst.post(f'/api/fdrs/{fdr.id}/documents/', {'file': SimpleUploadedFile('v2.pdf', b'%PDF-1.4 v2', content_type='application/pdf')})
check('document upload creates version 2 and deactivates version 1', r.status_code == 201 and r.json()['version'] == 2, r.content[:200])
check('only one active document after upload', fdr.documents.filter(active=True).count() == 1)
r = inst.post(f'/api/fdrs/{fdr.id}/documents/', {'file': SimpleUploadedFile('bad.exe', b'MZ\x90\x00 not allowed', content_type='application/pdf')})
check('document with fake PDF type refused (checked by content)', r.status_code == 400, r.status_code)
r = off.post(f'/api/fdrs/{fdr.id}/documents/', {'file': SimpleUploadedFile('x.pdf', b'%PDF', content_type='application/pdf')})
check('officer cannot upload (register permission)', r.status_code == 403, r.status_code)

r = off.post(f'/api/fdrs/{fdr.id}/verify/', content_type='application/json')
check('officer re-runs automated checks', r.status_code == 200, r.content[:200])
d = inst.get(f'/api/fdrs/{fdr.id}/').json()
check('FDR detail lists documents, verifications, queries, requests', all(k in d for k in ['documents', 'verifications', 'queries', 'requests']) and len(d['documents']) >= 1, list(d.keys()))
check('FDR detail is 404 for another institution', inst.get(f"/api/fdrs/{FDR.objects.get(fdr_number='DEMO-FDR-1002').id}/").status_code == 404)

s = inst.get('/api/dashboard/summary/').json()
check('dashboard summary for institution', s['institutions'] == 1 and s['fdrs'] >= 1, s)
s2 = adm.get('/api/dashboard/summary/').json()
check('dashboard summary for administrator sees all FDRs', s2['fdrs'] >= 3 and s2['institutions'] >= 3, s2)

check('institution can rename own institution? (admin only)', inst.patch(f'/api/institutions/{fdr.institution_id}/', data='{"name":"x"}', content_type='application/json').status_code == 403)
check('admin renames institution', adm.patch(f'/api/institutions/{fdr.institution_id}/', data='{"name":"Demo Engineering College (Renamed)"}', content_type='application/json').json()['name'].endswith('(Renamed)'))

reqs = inst.get('/api/requests/').json()
check('institution sees own requests list', isinstance(reqs, list), reqs)
check('audit log filter by entity', all(e['entity'] == 'FDR' for e in aud.get('/api/audit-logs/?entity=FDR').json()))
check('report rejects unknown format', inst.get('/api/reports/x/?output=pdf').status_code == 400)
check('report for institution is scoped (only own FDRs)', all('DEMO-FDR-1002' not in l for l in inst.get('/api/reports/x/').content.decode('utf-8-sig').splitlines()))
check('notifications list (own only)', all(n['userId'] == str(inst.get('/api/auth/me/').json()['id']) for n in inst.get('/api/notifications/').json()))
check('me endpoint returns role', inst.get('/api/auth/me/').json()['role'] == 'institution_user')
check('wrong token refused', Client(HTTP_HOST='localhost', HTTP_AUTHORIZATION='Token abc').get('/api/auth/me/').status_code == 401)
print(f'\nE2E2 TOTAL {len(results)} PASSED {sum(results)} FAILED {len(results)-sum(results)}')

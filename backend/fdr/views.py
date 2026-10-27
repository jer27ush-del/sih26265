"""HTTP layer. Parses requests, calls one service, returns JSON. No business rules live here."""
import csv
import io
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db.models import Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import domain, services
from .domain import DomainError
from .errors import Forbidden, NotFound
from .models import FDR, AuditLog, Document, Institution, Notification, Query, Request, SystemSettings, User, Verification
from .serializers import (audit_json, document_json, fdr_json, institution_json, notification_json, query_json,
                          request_json, user_json, verification_json)


def _parse_date(value, field):
    return domain.parse_iso_date(value or '', field)


def _as_int(value):
    """Multipart forms send every field as text, so numbers must be converted here (None stays None)."""
    if value is None or value == '':
        return None
    try:
        return int(str(value).strip())
    except ValueError as exc:
        raise DomainError('Enter a whole number of paise for the amount.') from exc


def _as_float(value, default=0.0):
    if value is None or value == '':
        return default
    try:
        return float(str(value).strip())
    except ValueError as exc:
        raise DomainError('Enter a valid interest rate.') from exc


def _as_bool(value, default):
    """Accepts real booleans (JSON) and text such as 'true'/'false' (multipart). Note bool('false') is True in Python."""
    if value is None or value == '':
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _fdr_input(body):
    """Maps the frontend's camelCase registration body to the snake_case fields the domain expects."""
    return {
        'institution_id': body.get('institutionId') or None,
        'fdr_number': body.get('fdrNumber', ''),
        'bank': body.get('bank', ''),
        'branch': body.get('branch', ''),
        'amount_paise': _as_int(body.get('amountPaise')),
        'issue_date': body.get('issueDate', ''),
        'maturity_date': body.get('maturityDate', ''),
        'interest_rate': _as_float(body.get('interestRate')),
        'payout_type': body.get('payoutType') or 'cumulative',
        'category': body.get('category', ''),
        'lien_marked': _as_bool(body.get('lienMarked'), False),
        'held_in_favour_of_aicte': _as_bool(body.get('heldInFavourOfAICTE'), True),
    }


def _ip(request):
    return request.META.get('REMOTE_ADDR')


def _visible_institutions(user):
    qs = Institution.objects.all()
    return qs.filter(pk=user.institution_id) if user.role == domain.ROLE_INSTITUTION else qs


# ----------------------------------------------------------------- authentication
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = str(request.data.get('email', '')).strip()
        password = str(request.data.get('password', ''))
        user = authenticate(request, username=email, password=password)
        if user is None or not user.is_active:
            return Response({'code': 'invalid_login', 'message': 'Invalid email or password.', 'fields': {}},
                            status=status.HTTP_400_BAD_REQUEST)
        user.last_login = timezone.now()
        user.save(update_fields=['last_login'])
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': user_json(user)})


class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    def get(self, request):
        return Response(user_json(request.user))


class DemoUsersView(APIView):
    """Demo only. Lists accounts for the role switcher. Disabled unless FDR_DEMO_MODE is on."""
    permission_classes = [AllowAny]

    def get(self, request):
        if not settings.DEMO_MODE:
            raise Forbidden('Demo accounts are disabled.')
        return Response([user_json(u) for u in User.objects.filter(is_active=True).order_by('role', 'name')])


class DemoSwitchView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.DEMO_MODE:
            raise Forbidden('Demo accounts are disabled.')
        user = User.objects.filter(pk=request.data.get('userId'), is_active=True).first()
        if not user:
            raise NotFound()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({'token': token.key, 'user': user_json(user)})


# ----------------------------------------------------------------- institutions
class InstitutionsView(APIView):
    def get(self, request):
        return Response([institution_json(i) for i in _visible_institutions(request.user)])

    def post(self, request):
        user = request.user
        services.require(user, 'manage_institutions')
        code = str(request.data.get('code', '')).strip()
        name = str(request.data.get('name', '')).strip()
        if not code or not name:
            raise DomainError('Institution code and name are required.')
        if Institution.objects.filter(code__iexact=code).exists():
            raise DomainError('Institution code already exists.')
        inst = Institution.objects.create(code=code, name=name, state=request.data.get('state', ''),
                                          contact_name=request.data.get('contactName', ''),
                                          email=request.data.get('email', ''), phone=request.data.get('phone', ''))
        services.audit(user, 'institution.created', 'Institution', inst.id, None, institution_json(inst), _ip(request))
        return Response(institution_json(inst), status=status.HTTP_201_CREATED)


class InstitutionDetailView(APIView):
    def patch(self, request, pk):
        user = request.user
        services.require(user, 'manage_institutions')
        try:
            inst = Institution.objects.get(pk=pk)
        except (Institution.DoesNotExist, ValueError):
            raise NotFound()
        old = institution_json(inst)
        for camel, field in (('name', 'name'), ('state', 'state'), ('contactName', 'contact_name'),
                             ('email', 'email'), ('phone', 'phone')):
            if camel in request.data:
                setattr(inst, field, str(request.data[camel]).strip())
        if 'code' in request.data:
            code = str(request.data['code']).strip()
            if Institution.objects.filter(code__iexact=code).exclude(pk=inst.pk).exists():
                raise DomainError('Institution code already exists.')
            inst.code = code
        if request.data.get('status') in ('Active', 'Inactive'):
            inst.is_active = request.data['status'] == 'Active'
        inst.save()
        services.audit(user, 'institution.updated', 'Institution', inst.id, old, institution_json(inst), _ip(request))
        return Response(institution_json(inst))


# ----------------------------------------------------------------- FDRs
class FdrsView(APIView):
    def get(self, request):
        qs = services.visible_fdrs(request.user)
        if request.query_params.get('status'):
            qs = qs.filter(status=request.query_params['status'])
        if request.query_params.get('bank'):
            qs = qs.filter(bank__icontains=request.query_params['bank'])
        search = request.query_params.get('q', '').strip()
        if search:
            qs = qs.filter(Q(fdr_number__icontains=search) | Q(bank__icontains=search) | Q(branch__icontains=search))
        return Response([fdr_json(f) for f in qs])

    def post(self, request):
        upload = request.FILES.get('file')
        fdr = services.register_fdr(request.user, _fdr_input(request.data), upload=upload, ip=_ip(request))
        return Response(fdr_json(fdr), status=status.HTTP_201_CREATED)


class FdrDetailView(APIView):
    def get(self, request, pk):
        try:
            fdr = services.visible_fdrs(request.user).get(pk=pk)
        except (FDR.DoesNotExist, ValueError):
            raise NotFound()
        return Response({
            **fdr_json(fdr),
            'documents': [document_json(d) for d in fdr.documents.all()],
            'verifications': [verification_json(v) for v in fdr.verifications.all()],
            'queries': [query_json(q) for q in fdr.queries.all()],
            'requests': [request_json(r) for r in fdr.requests.all()],
        })


class FdrImportView(APIView):
    """Accepts a CSV file (multipart field 'file') or JSON {rows: [[...]]}. Bad rows are reported, good rows are saved."""

    def post(self, request):
        upload = request.FILES.get('file')
        if upload:
            rows = domain.parse_csv_text(upload.read().decode('utf-8-sig', errors='replace'))
        else:
            rows = request.data.get('rows') or []
            if not isinstance(rows, list):
                raise DomainError('Rows must be a list of lists.')
        return Response(services.import_rows(request.user, rows, ip=_ip(request)))


class DocumentUploadView(APIView):
    def post(self, request, pk):
        upload = request.FILES.get('file')
        if not upload:
            raise DomainError('Attach a file.')
        doc = services.add_document(request.user, pk, upload, ip=_ip(request))
        return Response(document_json(doc), status=status.HTTP_201_CREATED)


class DocumentDownloadView(APIView):
    def get(self, request, pk):
        doc, path = services.document_for_download(request.user, pk)
        if not path.exists():
            raise NotFound()
        response = FileResponse(open(path, 'rb'), content_type=doc.mime_type)
        response['Content-Disposition'] = f'attachment; filename="{doc.original_name}"'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


class VerifyView(APIView):
    def post(self, request, pk):
        fdr = services.rerun_verification(request.user, pk, ip=_ip(request))
        return Response(fdr_json(fdr))


class TransitionView(APIView):
    def post(self, request, pk):
        fdr = services.transition(request.user, pk, request.data.get('status', ''),
                                  request.data.get('reason', ''), ip=_ip(request))
        return Response(fdr_json(fdr))


class BankConfirmationView(APIView):
    def post(self, request, pk):
        data = {
            'date': _parse_date(request.data.get('date'), 'confirmation date'),
            'officer': request.data.get('officer', ''),
            'mode': request.data.get('mode', ''),
            'reference': request.data.get('reference', ''),
        }
        verification = services.record_bank_confirmation(request.user, pk, data, ip=_ip(request))
        return Response(verification_json(verification))


class FdrRequestView(APIView):
    def post(self, request, pk):
        req = services.add_request(request.user, pk, request.data.get('type', ''),
                                   request.data.get('reason', ''), ip=_ip(request))
        return Response(request_json(req), status=status.HTTP_201_CREATED)


class QueryReplyView(APIView):
    def post(self, request, pk):
        query = services.reply_to_query(request.user, pk, request.data.get('reply', ''), ip=_ip(request))
        return Response(query_json(query))


class RequestsView(APIView):
    def get(self, request):
        visible = services.visible_fdrs(request.user).values_list('pk', flat=True)
        qs = Request.objects.filter(fdr_id__in=visible)
        if request.user.role == domain.ROLE_INSTITUTION:
            qs = qs.filter(submitted_by=request.user)
        return Response([request_json(r) for r in qs])


class RequestRecommendView(APIView):
    def post(self, request, pk):
        req = services.recommend_request(request.user, pk, ip=_ip(request))
        return Response(request_json(req))


class RequestDecisionView(APIView):
    def post(self, request, pk):
        req = services.decide_request(request.user, pk, request.data.get('decision', ''),
                                      request.data.get('reason', ''), ip=_ip(request))
        return Response(request_json(req))


# ----------------------------------------------------------------- workspace, dashboard, reports
class WorkspaceView(APIView):
    """One call that returns everything the workspace screens need, scoped to the caller's role."""

    def get(self, request):
        user = request.user
        fdrs = services.visible_fdrs(user)
        fdr_ids = list(fdrs.values_list('pk', flat=True))
        users = User.objects.all() if user.role == domain.ROLE_ADMIN else User.objects.filter(pk=user.pk)
        audit = []
        if domain.can_view_audit(user.role):
            entries = AuditLog.objects.select_related('actor').all()
            if user.role == domain.ROLE_OFFICER:
                entries = entries.filter(entity__in=['FDR', 'Verification'])
            audit = [audit_json(a) for a in entries[:500]]
        return Response({
            'institutions': [institution_json(i) for i in _visible_institutions(user)],
            'users': [user_json(u) for u in users],
            'fdrs': [fdr_json(f) for f in fdrs],
            'documents': [document_json(d) for d in Document.objects.filter(fdr_id__in=fdr_ids)],
            'verifications': [verification_json(v) for v in Verification.objects.filter(fdr_id__in=fdr_ids)],
            'queries': [query_json(q) for q in Query.objects.filter(fdr_id__in=fdr_ids)],
            'requests': [request_json(r) for r in Request.objects.filter(fdr_id__in=fdr_ids)],
            'notifications': [notification_json(n) for n in Notification.objects.filter(user=user)],
            'auditLogs': audit,
            'settings': SystemSettings.load().data,
        })


class DashboardSummaryView(APIView):
    def get(self, request):
        fdrs = services.visible_fdrs(request.user)
        today = timezone.localdate()
        pending = fdrs.filter(status__in=['Submitted', 'Under Verification', 'Corrected', 'Query Raised']).count()
        return Response({
            'institutions': _visible_institutions(request.user).count(),
            'fdrs': fdrs.count(),
            'pending': pending,
            'flagged': fdrs.filter(review_flag=True).count(),
            'maturingWithin90Days': fdrs.filter(maturity_date__gte=today,
                                                maturity_date__lte=today + timedelta(days=90)).count(),
        })


class ReportView(APIView):
    def get(self, request, name):
        services.require(request.user, 'view_reports')
        rows = [['FDR Number', 'Institution', 'State', 'Bank', 'Amount INR', 'Status', 'Maturity Date']]
        for f in services.visible_fdrs(request.user):
            rows.append([f.fdr_number, f.institution.name, f.institution.state, f.bank,
                         domain.paise_to_decimal(f.amount_paise), f.status, f.maturity_date.isoformat()])
        # Not 'format': DRF reserves that query parameter for choosing a renderer.
        if request.query_params.get('output', 'csv') != 'csv':
            raise DomainError('Only CSV export is available in this build.')
        buffer = io.StringIO()
        csv.writer(buffer).writerows(rows)
        response = HttpResponse('\ufeff' + buffer.getvalue(), content_type='text/csv; charset=utf-8')
        safe = ''.join(c for c in name if c.isalnum() or c in '-_') or 'report'
        response['Content-Disposition'] = f'attachment; filename="{safe}.csv"'
        return response


class NotificationsView(APIView):
    def get(self, request):
        return Response([notification_json(n) for n in Notification.objects.filter(user=request.user)])


class NotificationReadView(APIView):
    def post(self, request, pk):
        return Response(notification_json(services.mark_notification_read(request.user, pk)))


class AuditLogsView(APIView):
    def get(self, request):
        user = request.user
        if not domain.can_view_audit(user.role):
            raise Forbidden('Your role cannot view the audit log.')
        qs = AuditLog.objects.select_related('actor')
        if user.role == domain.ROLE_OFFICER:
            qs = qs.filter(entity__in=['FDR', 'Verification'])
        if request.query_params.get('entity'):
            qs = qs.filter(entity=request.query_params['entity'])
        return Response([audit_json(a) for a in qs[:1000]])


class SettingsView(APIView):
    def get(self, request):
        return Response(SystemSettings.load().data)

    def put(self, request):
        data = dict(SystemSettings.load().data)
        data.update(request.data)
        return Response(services.update_settings(request.user, data, ip=_ip(request)))

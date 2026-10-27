from django.urls import path

from . import views

urlpatterns = [
    path('auth/login/', views.LoginView.as_view()),
    path('auth/logout/', views.LogoutView.as_view()),
    path('auth/me/', views.MeView.as_view()),
    path('auth/demo-users/', views.DemoUsersView.as_view()),
    path('auth/demo-switch/', views.DemoSwitchView.as_view()),
    path('workspace/', views.WorkspaceView.as_view()),
    path('dashboard/summary/', views.DashboardSummaryView.as_view()),
    path('institutions/', views.InstitutionsView.as_view()),
    path('institutions/<uuid:pk>/', views.InstitutionDetailView.as_view()),
    path('fdrs/', views.FdrsView.as_view()),
    path('fdrs/import/', views.FdrImportView.as_view()),
    path('fdrs/<uuid:pk>/', views.FdrDetailView.as_view()),
    path('fdrs/<uuid:pk>/documents/', views.DocumentUploadView.as_view()),
    path('fdrs/<uuid:pk>/verify/', views.VerifyView.as_view()),
    path('fdrs/<uuid:pk>/transition/', views.TransitionView.as_view()),
    path('fdrs/<uuid:pk>/bank-confirmation/', views.BankConfirmationView.as_view()),
    path('fdrs/<uuid:pk>/requests/', views.FdrRequestView.as_view()),
    path('documents/<uuid:pk>/download/', views.DocumentDownloadView.as_view()),
    path('queries/<uuid:pk>/reply/', views.QueryReplyView.as_view()),
    path('requests/', views.RequestsView.as_view()),
    path('requests/<uuid:pk>/recommend/', views.RequestRecommendView.as_view()),
    path('requests/<uuid:pk>/decision/', views.RequestDecisionView.as_view()),
    path('reports/<str:name>/', views.ReportView.as_view()),
    path('notifications/', views.NotificationsView.as_view()),
    path('notifications/<uuid:pk>/read/', views.NotificationReadView.as_view()),
    path('audit-logs/', views.AuditLogsView.as_view()),
    path('settings/', views.SettingsView.as_view()),
]

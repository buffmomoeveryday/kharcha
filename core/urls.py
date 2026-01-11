from django.contrib import admin
from django.urls import path

from apps.users import views as u_views
from apps.dashboard import views as d_views
from apps.income import views as inc_views
from apps.expenses import views as exp_views
from apps.accounts import views as a_views


def redirect_to_dashboard(request):
    from django.shortcuts import redirect

    return redirect("dashboard")


urlpatterns = [
    path("quick-add", d_views.quick_add_category, name="quick_add_category"),
    path("", redirect_to_dashboard),
    path("all", d_views.all_transactions_view, name="all_transactions"),
    path("admin/", admin.site.urls),
    path("users/registration", u_views.registration_view, name="registration"),
    path("users/login", u_views.login_view, name="login"),
    path("users/logout", u_views.logout_view, name="logout"),
    path("dashboard/", d_views.dashboard_view, name="dashboard"),
    path("accounts/dashboard/", a_views.accounts_dashboard, name="accounts_dashboard"),
    path("accounts/debt-dashboard/", a_views.debt_dashboard, name="debt_page"),
    path(
        "accounts/process-transfer/", a_views.process_transfer, name="process_transfer"
    ),
    path("export/", d_views.export_report_pdf, name="export_pdf"),
    path("dashboard/export/", d_views.export_report_csv, name="export_report"),
    path("income/", inc_views.income_list_view, name="income_page"),
    path("expenses/list/", exp_views.expense_list, name="expense_list"),
    path("expenses/add/", exp_views.add_expense, name="add_expense"),
    path("expenses/edit/<int:pk>/", exp_views.edit_expense, name="edit_expense"),
    path("expenses/delete/<int:pk>/", exp_views.delete_expense, name="delete_expense"),
    path("categories/", d_views.category_list, name="category_list"),
    path("categories/manage/", d_views.manage_category, name="manage_category"),
    path(
        "categories/delete/<int:pk>/", d_views.delete_category, name="delete_category"
    ),
]

import base64
import csv
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from itertools import chain

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.offline as opy
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.utils import timezone
from plotly.offline import plot
from xhtml2pdf import pisa

from apps.expenses.models import Expense
from apps.income.models import Income

from .models import Category


def _get_plot_image(fig):
    try:
        img_bytes = fig.to_image(format="png", engine="kaleido", width=800, height=400)
        encoding = base64.b64encode(img_bytes).decode("utf-8")
        return f"data:image/png;base64,{encoding}"
    except Exception as e:
        print(f"Chart Error: {e}")
        return None


def _get_dashboard_data(user, start_date, end_date):
    # 1. Base Querysets
    income_base = Income.objects.filter(
        user=user, is_active=True, date_received__range=[start_date, end_date]
    ).select_related("category")

    expense_base = Expense.objects.filter(
        user=user, is_active=True, date_spent__range=[start_date, end_date]
    ).select_related("category")

    # 2. Key Metrics
    total_income = income_base.aggregate(Sum("amount"))["amount__sum"] or Decimal(0)
    total_expense = expense_base.aggregate(Sum("amount"))["amount__sum"] or Decimal(0)

    total_recurring = expense_base.filter(
        is_recurring=True, recurring_interval="monthly"
    ).aggregate(Sum("amount"))["amount__sum"] or Decimal(0)

    # 3. Budget & Summary Logic
    budget_data = []
    current_month = timezone.now().month
    current_year = timezone.now().year

    categories = Category.objects.filter(user=user, category_type="expense")
    for cat in categories:
        spent_this_month = Expense.objects.filter(
            user=user,
            category=cat,
            is_active=True,
            date_spent__month=current_month,
            date_spent__year=current_year,
        ).aggregate(Sum("amount"))["amount__sum"] or Decimal(0)

        limit = cat.budget_limit or Decimal(0)
        # Convert to float for percentage calculation
        percent = (float(spent_this_month) / float(limit) * 100) if limit > 0 else 0
        remaining = limit - spent_this_month

        budget_data.append(
            {
                "name": cat.name,
                "spent": spent_this_month,
                "limit": limit,
                "remaining": remaining,
                "percent": percent,
                "is_alert": percent >= 80 and limit > 0,
            }
        )

    # 4. Chart 1: Cash Flow (Line Chart) - FIXED TYPE ISSUE
    chart_html = "<p class='text-center text-muted py-5'>No trend data available</p>"

    # Prep Income Data
    df_inc_raw = pd.DataFrame(
        list(income_base.values("date_received").annotate(total=Sum("amount")))
    )
    if not df_inc_raw.empty:
        df_inc = df_inc_raw.rename(columns={"date_received": "Date", "total": "Income"})
    else:
        df_inc = pd.DataFrame(columns=["Date", "Income"])

    # Prep Expense Data
    df_exp_raw = pd.DataFrame(
        list(expense_base.values("date_spent").annotate(total=Sum("amount")))
    )
    if not df_exp_raw.empty:
        df_exp = df_exp_raw.rename(columns={"date_spent": "Date", "total": "Expense"})
    else:
        df_exp = pd.DataFrame(columns=["Date", "Expense"])

    if not df_inc.empty or not df_exp.empty:
        # Merge and fill missing values
        df_merged = pd.merge(df_inc, df_exp, on="Date", how="outer").fillna(0)

        # --- FIX: Ensure types are identical for Plotly Wide-Form ---
        df_merged["Date"] = pd.to_datetime(df_merged["Date"])
        df_merged["Income"] = df_merged["Income"].astype(float)
        df_merged["Expense"] = df_merged["Expense"].astype(float)
        df_merged = df_merged.sort_values("Date")

        fig = px.line(
            df_merged,
            x="Date",
            y=["Income", "Expense"],
            template="plotly_white",
            color_discrete_map={"Income": "#198754", "Expense": "#dc3545"},
        )
        fig.update_layout(
            margin=dict(l=5, r=5, t=10, b=5),
            height=300,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
            ),
            xaxis_title=None,
            yaxis_title=None,
        )
        chart_html = plot(fig, auto_open=False, output_type="div")

    # 5. Chart 2: Expense Distribution (Pie Chart)
    cat_qs = expense_base.values("category__name").annotate(total=Sum("amount"))
    pie_chart_html = "<p class='text-center text-muted py-5'>No expense categories</p>"

    if cat_qs.exists():
        df_cat = pd.DataFrame(list(cat_qs))
        df_cat["total"] = df_cat["total"].astype(float)  # Fix Decimal issue

        pie_fig = px.pie(
            df_cat,
            values="total",
            names="category__name",
            hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Safe,
        )
        pie_fig.update_layout(margin=dict(l=5, r=5, t=10, b=5), height=300)
        pie_chart_html = plot(pie_fig, auto_open=False, output_type="div")

    # 6. Recent Transactions List
    # Combine and sort by date (using actual model date fields)
    recent_inc = list(income_base.order_by("-date_received")[:5])
    recent_exp = list(expense_base.order_by("-date_spent")[:5])

    recent_transactions = sorted(
        chain(recent_inc, recent_exp),
        key=lambda x: getattr(x, "date_received", getattr(x, "date_spent", None)),
        reverse=True,
    )[:8]

    return {
        "total_income": total_income,
        "total_expense": total_expense,
        "total_recurring": total_recurring,
        "budget_data": budget_data,
        "chart_html": chart_html,
        "pie_chart_html": pie_chart_html,
        "recent_transactions": recent_transactions,
        "start_date": start_date,
        "end_date": end_date,
    }


@login_required
def dashboard_view(request):
    start_date_str = request.GET.get("start")
    end_date_str = request.GET.get("end")

    try:
        if start_date_str:
            start_date = timezone.datetime.strptime(start_date_str, "%Y-%m-%d").date()
        else:
            start_date = timezone.now().date() - timedelta(days=30)

        if end_date_str:
            end_date = timezone.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        else:
            end_date = timezone.now().date()
    except ValueError:
        # Fallback if date parsing fails
        start_date = timezone.now().date() - timedelta(days=30)
        end_date = timezone.now().date()

    context = _get_dashboard_data(request.user, start_date, end_date)
    return render(request, "dashboard/dashboard.html", context)


@login_required
def quick_add_category(request):
    if request.method == "POST":
        name = request.POST.get("name")
        cat_type = request.POST.get("category_type")
        limit = request.POST.get("budget_limit") or 0

        Category.objects.create(
            user=request.user, name=name, category_type=cat_type, budget_limit=limit
        )
    return redirect("dashboard")


@login_required
def export_report_csv(request):
    start_str = request.GET.get("start")
    end_str = request.GET.get("end")

    income_qs = Income.objects.filter(user=request.user, is_active=True).select_related(
        "category"
    )
    expense_qs = Expense.objects.filter(
        user=request.user, is_active=True
    ).select_related("category")

    if start_str and end_str:
        income_qs = income_qs.filter(date_received__range=[start_str, end_str])
        expense_qs = expense_qs.filter(date_spent__range=[start_str, end_str])

    response = HttpResponse(content_type="text/csv")
    filename = f"Financial_Report_{timezone.now().date()}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Type",
            "Title/Source",
            "Category",
            "Amount",
            "Currency",
            "Date",
            "Payment Method",
            "Notes",
        ]
    )

    # FIX: Use .category.name instead of just .category
    for inc in income_qs:
        writer.writerow(
            [
                "Income",
                inc.source,
                inc.category.name if inc.category else "Uncategorized",
                inc.amount,
                inc.currency,
                inc.date_received,
                inc.payment_method,
                inc.notes,
            ]
        )

    for exp in expense_qs:
        writer.writerow(
            [
                "Expense",
                exp.title,
                exp.category.name if exp.category else "Uncategorized",
                exp.amount,
                exp.currency,
                exp.date_spent,
                exp.payment_method,
                exp.notes,
            ]
        )

    return response


@login_required
def export_report_pdf(request):
    # 1. Capture Filters
    period = request.GET.get("period", "this_month")
    report_type = request.GET.get("type")  # 'income', 'expense', or None
    query = request.GET.get("q")
    category_id = request.GET.get("category", None)

    print("---------")
    print(category_id)
    print("---------")

    # 2. Base Querysets
    income_qs = Income.objects.filter(user=request.user, is_active=True)
    expense_qs = Expense.objects.filter(user=request.user, is_active=True)

    # FIX: Check if category_id is specifically the string "None" or empty
    if category_id and category_id != "None" and category_id != "":
        expense_qs = expense_qs.filter(category_id=category_id)
        income_qs = income_qs.filter(category_id=category_id)

    # 3. Apply Date Filtering (Matches expense_list logic)
    today = timezone.now().date()
    start_date = None

    if period == "last_week":
        start_date = today - timedelta(days=7)
    elif period == "this_month":
        start_date = today.replace(day=1)
    elif period == "last_month":
        first_this = today.replace(day=1)
        end_date = first_this - timedelta(days=1)
        start_date = end_date.replace(day=1)
        # Specific override for last month
        income_qs = income_qs.filter(date_received__range=[start_date, end_date])
        expense_qs = expense_qs.filter(date_spent__range=[start_date, end_date])
    elif period == "last_year":
        last_year = today.year - 1
        income_qs = income_qs.filter(date_received__year=last_year)
        expense_qs = expense_qs.filter(date_spent__year=last_year)

    if start_date and period not in ["last_month", "last_year", "all"]:
        income_qs = income_qs.filter(date_received__gte=start_date)
        expense_qs = expense_qs.filter(date_spent__gte=start_date)

    # 4. Apply Search/Category & Type Filters
    if query:
        expense_qs = expense_qs.filter(title__icontains=query)
    if category_id:
        expense_qs = expense_qs.filter(category_id=category_id)
        income_qs = income_qs.filter(category_id=category_id)

    if report_type == "income":
        expense_qs = expense_qs.none()
    elif report_type == "expense":
        income_qs = income_qs.none()

    # 5. Calculations
    total_income = income_qs.aggregate(Sum("amount"))["amount__sum"] or 0
    total_expense = expense_qs.aggregate(Sum("amount"))["amount__sum"] or 0
    balance = total_income - total_expense

    # 6. Generate Charts
    line_chart = None
    pie_chart = None

    df_inc = pd.DataFrame(list(income_qs.values("date_received", "amount"))).rename(
        columns={"date_received": "Date"}
    )
    df_exp = pd.DataFrame(list(expense_qs.values("date_spent", "amount"))).rename(
        columns={"date_spent": "Date"}
    )

    if not df_inc.empty or not df_exp.empty:
        df_inc = (
            df_inc.groupby("Date")["amount"].sum().reset_index(name="Income")
            if not df_inc.empty
            else pd.DataFrame(columns=["Date", "Income"])
        )
        df_exp = (
            df_exp.groupby("Date")["amount"].sum().reset_index(name="Expense")
            if not df_exp.empty
            else pd.DataFrame(columns=["Date", "Expense"])
        )
        df_merged = (
            pd.merge(df_inc, df_exp, on="Date", how="outer")
            .fillna(0)
            .sort_values("Date")
        )

        cols = [
            c
            for c in ["Income", "Expense"]
            if c in df_merged.columns and df_merged[c].any()
        ]
        if cols:
            fig_line = px.line(
                df_merged,
                x="Date",
                y=cols,
                template="plotly_white",
                color_discrete_map={"Income": "#198754", "Expense": "#dc3545"},
            )
            line_chart = _get_plot_image(fig_line)

    if report_type != "income" and expense_qs.exists():
        cat_df = pd.DataFrame(
            list(expense_qs.values("category__name").annotate(total=Sum("amount")))
        )
        fig_pie = px.pie(cat_df, values="total", names="category__name", hole=0.3)
        pie_chart = _get_plot_image(fig_pie)

    # 7. Render PDF Response
    context = {
        "income": income_qs.order_by("-date_received"),
        "expenses": expense_qs.order_by("-date_spent"),
        "total_income": total_income,
        "total_expense": total_expense,
        "balance": balance,
        "line_chart": line_chart,
        "pie_chart": pie_chart,
        "report_type": report_type,
        "period": period.replace("_", " ").title(),
        "user": request.user,
        "today": today,
    }

    template = get_template("dashboard/report_pdf.html")
    html = template.render(context)
    result = BytesIO()
    pisa.pisaDocument(BytesIO(html.encode("UTF-8")), result)

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    filename = f"Kharcha_{report_type or 'Report'}_{today}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@login_required
def all_transactions_view(request):
    # 1. Setup Base Querysets
    incomes = Income.objects.filter(user=request.user, is_active=True)
    expenses = Expense.objects.filter(user=request.user, is_active=True)

    # 2. Date Filtering Logic
    period = request.GET.get("period", "this_month")
    today = timezone.now().date()
    start_date = None

    if period == "last_week":
        start_date = today - timedelta(days=7)
    elif period == "this_month":
        start_date = today.replace(day=1)
    elif period == "last_month":
        first_this = today.replace(day=1)
        start_date = (first_this - timedelta(days=1)).replace(day=1)
        end_month = first_this - timedelta(days=1)
        incomes = incomes.filter(date_received__range=[start_date, end_month])
        expenses = expenses.filter(date_spent__range=[start_date, end_month])
    elif period == "last_year":
        start_date = today.replace(year=today.year - 1, month=1, day=1)
        end_year = today.replace(year=today.year - 1, month=12, day=31)
        incomes = incomes.filter(date_received__range=[start_date, end_year])
        expenses = expenses.filter(date_spent__range=[start_date, end_year])

    # Apply start_date filter for ongoing periods (week/this month)
    if start_date and period not in ["last_month", "last_year", "all"]:
        incomes = incomes.filter(date_received__gte=start_date)
        expenses = expenses.filter(date_spent__gte=start_date)

    # 3. Merge and Sort for Table
    all_list = sorted(
        chain(incomes, expenses),
        key=lambda x: x.date_received if hasattr(x, "date_received") else x.date_spent,
        reverse=True,
    )

    # 4. Projection Logic (Last 30 Days Trend)
    # We always use 30 days of history for a stable projection, regardless of filter
    hist_start = today - timedelta(days=30)
    date_range = pd.date_range(start=hist_start, end=today)
    df_balance = pd.DataFrame({"Date": date_range, "Amount": 0.0})

    # Get data specifically for the chart
    chart_inc = Income.objects.filter(
        user=request.user, date_received__range=[hist_start, today]
    )
    chart_exp = Expense.objects.filter(
        user=request.user, date_spent__range=[hist_start, today]
    )

    for inc in chart_inc:
        df_balance.loc[
            df_balance["Date"] == pd.Timestamp(inc.date_received), "Amount"
        ] += float(inc.amount)
    for exp in chart_exp:
        df_balance.loc[
            df_balance["Date"] == pd.Timestamp(exp.date_spent), "Amount"
        ] -= float(exp.amount)

    df_balance["Cumulative"] = df_balance["Amount"].cumsum()

    # Regression
    y = df_balance["Cumulative"].values
    x = np.arange(len(y))
    slope, intercept = np.polyfit(x, y, 1)

    future_x = np.arange(len(y), len(y) + 30)
    future_dates = pd.date_range(start=today + timedelta(days=1), periods=30)
    projection = slope * future_x + intercept

    # 5. Create Chart
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df_balance["Date"],
            y=df_balance["Cumulative"],
            name="History",
            line=dict(color="#0d6efd", width=3),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=future_dates,
            y=projection,
            name="Projected",
            line=dict(color="#6c757d", dash="dot"),
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=350,
        margin=dict(l=0, r=0, t=30, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    projection_html = opy.plot(fig, auto_open=False, output_type="div")

    # 6. Pagination
    paginator = Paginator(all_list, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "dashboard/all_transactions.html",
        {
            "transactions": page_obj,
            "projection_chart": projection_html,
            "current_period": period,
        },
    )


@login_required
def category_list(request):
    # 1. Base Queryset
    categories_qs = (
        Category.objects.filter(user=request.user)
        .annotate(item_count=Count("expense") + Count("income"))
        .order_by("name")
    )

    # 2. Filters
    query = request.GET.get("q")
    cat_type = request.GET.get("type")  # 'income' or 'expense'

    if query:
        categories_qs = categories_qs.filter(name__icontains=query)
    if cat_type:
        categories_qs = categories_qs.filter(category_type=cat_type)

    # 3. Chart Generation (Distribution of Category Types)
    pie_chart_div = None
    if categories_qs.exists():
        df = pd.DataFrame(list(categories_qs.values("name", "category_type")))
        fig = px.pie(
            df,
            names="category_type",
            title="Category Type Distribution",
            hole=0.4,
            color_discrete_map={"income": "#198754", "expense": "#dc3545"},
        )
        fig.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=300)
        pie_chart_div = plot(fig, output_type="div")

    context = {
        "categories": categories_qs,
        "chart_pie": pie_chart_div,
        "search_query": query or "",
        "current_type": cat_type or "",
        "today": timezone.now(),
    }
    return render(request, "dashboard/category_list.html", context)


@login_required
def manage_category(request):
    if request.method == "POST":
        category_id = request.POST.get("category_id")
        name = request.POST.get("name")
        category_type = request.POST.get("category_type")

        if category_id:
            # --- Update Logic ---
            category = get_object_or_404(Category, id=category_id, user=request.user)
            category.name = name
            category.category_type = category_type
            category.save()
            messages.success(request, f"Category '{name}' updated successfully.")
        else:
            # --- Create Logic ---
            Category.objects.create(
                user=request.user, name=name, category_type=category_type
            )
            messages.success(request, f"Category '{name}' added successfully.")

    return redirect("category_list")


@login_required
def delete_category(request, pk):
    category = get_object_or_404(Category, id=pk, user=request.user)

    has_expenses = category.expense_set.exists()
    has_income = category.income_set.exists()

    if has_expenses or has_income:
        messages.error(
            request,
            "Cannot delete category: It is currently linked to existing records.",
        )
    else:
        category.delete()
        messages.success(request, "Category deleted successfully.")

    return redirect("category_list")

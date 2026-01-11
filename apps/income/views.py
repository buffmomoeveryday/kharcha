from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from django.db.models import Sum
from django.db import transaction
from django.core.paginator import Paginator
from decimal import Decimal
import pandas as pd
import plotly.express as px
import plotly.offline as opy
from datetime import timedelta

from .models import Income, Category
from apps.accounts.models import Account


@login_required
def income_list_view(request):
    if request.method == "POST":
        try:
            with transaction.atomic():
                source = request.POST.get("source")
                amount = Decimal(request.POST.get("amount") or 0)
                category_id = request.POST.get("category")
                account_id = request.POST.get("account")  # NEW: Account from form
                date_received = request.POST.get("date_received")
                is_recurring = request.POST.get("is_recurring") == "on"
                recurring_interval = request.POST.get("recurring_interval", "none")

                if source and amount > 0 and date_received and account_id:
                    category_obj = get_object_or_404(
                        Category, id=category_id, user=request.user
                    )
                    account_obj = get_object_or_404(
                        Account, id=account_id, user=request.user
                    )

                    Income.objects.create(
                        user=request.user,
                        source=source,
                        amount=amount,
                        account=account_obj,  # NEW: Linked to account
                        category=category_obj,
                        date_received=date_received,
                        is_recurring=is_recurring,
                        recurring_interval=recurring_interval,
                    )
                    messages.success(
                        request, f"NPR {amount} added to {account_obj.name}"
                    )
                    return redirect("income_page")
                else:
                    messages.error(
                        request, "Please fill all required fields correctly."
                    )
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    income_qs = (
        Income.objects.filter(user=request.user, is_active=True)
        .select_related("category", "account")
        .order_by("-date_received")
    )

    period = request.GET.get("period", "this_month")
    today = timezone.now().date()

    if period == "last_week":
        income_qs = income_qs.filter(date_received__gte=today - timedelta(days=7))
    elif period == "this_month":
        income_qs = income_qs.filter(
            date_received__year=today.year, date_received__month=today.month
        )
    elif period == "last_month":
        first_day_this_month = today.replace(day=1)
        last_day_last_month = first_day_this_month - timedelta(days=1)
        income_qs = income_qs.filter(
            date_received__year=last_day_last_month.year,
            date_received__month=last_day_last_month.month,
        )
    elif period == "last_year":
        income_qs = income_qs.filter(date_received__year=today.year - 1)

    # --- 3. SEARCH & CATEGORY FILTERS ---
    query = request.GET.get("q")
    category_id = request.GET.get("category")
    if query:
        income_qs = income_qs.filter(source__icontains=query)
    if category_id:
        income_qs = income_qs.filter(category_id=category_id)

    # --- 4. CHART GENERATION (FIXED TYPES) ---
    chart_trend, chart_pie = None, None
    if income_qs.exists():
        df = pd.DataFrame(
            list(income_qs.values("amount", "category__name", "date_received"))
        )

        # FIX: Force amount to float for Plotly compatibility
        df["amount"] = df["amount"].astype(float)
        df["date_received"] = pd.to_datetime(df["date_received"])

        # Trend Chart
        trend_df = (
            df.groupby("date_received")["amount"]
            .sum()
            .reset_index()
            .sort_values("date_received")
        )
        fig_trend = px.area(
            trend_df,
            x="date_received",
            y="amount",
            title="Income Flow",
            color_discrete_sequence=["#198754"],
            template="plotly_white",
        )
        fig_trend.update_layout(
            margin=dict(l=10, r=10, t=30, b=10), height=300, xaxis_title=None
        )
        chart_trend = opy.plot(fig_trend, auto_open=False, output_type="div")

        # Pie Chart
        fig_pie = px.pie(
            df,
            values="amount",
            names="category__name",
            title="Income Sources",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.Greens_r,
        )
        fig_pie.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=300)
        chart_pie = opy.plot(fig_pie, auto_open=False, output_type="div")

    # --- 5. PAGINATION ---
    paginator = Paginator(income_qs, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "incomes": page_obj,
        "categories": Category.objects.filter(
            user=request.user, category_type="income"
        ),
        "accounts": Account.objects.filter(user=request.user, is_active=True),
        "chart_trend": chart_trend,
        "chart_pie": chart_pie,
        "total_income": income_qs.aggregate(Sum("amount"))["amount__sum"] or 0,
        "today_date": today.strftime("%Y-%m-%d"),
        "search_query": query or "",
        "selected_category": category_id,
        "current_period": period,
    }
    return render(
        request,
        "income/income_page.html",
        context,
    )

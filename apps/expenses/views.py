from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Sum
from django.db import transaction
from django.core.exceptions import ValidationError
from datetime import date
import plotly.express as px
from plotly.offline import plot
import pandas as pd

from .models import Expense, Category
from apps.accounts.models import Account, Debt
from decimal import Decimal


@login_required
def expense_list(request):
    expenses_qs = (
        Expense.objects.filter(user=request.user, is_active=True)
        .select_related("category", "account")
        .order_by("-date_spent")
    )

    # --- 1. Filter Logic ---
    query = request.GET.get("q")
    category_id = request.GET.get("category")
    if query:
        expenses_qs = expenses_qs.filter(title__icontains=query)
    if category_id:
        expenses_qs = expenses_qs.filter(category_id=category_id)

    # --- 2. Financial Summary ---
    total_balance = (
        Account.objects.filter(user=request.user).aggregate(Sum("balance"))[
            "balance__sum"
        ]
        or 0
    )
    to_receive = (
        Debt.objects.filter(
            user=request.user, debt_type="receivable", is_settled=False
        ).aggregate(Sum("remaining_amount"))["remaining_amount__sum"]
        or 0
    )
    to_pay = (
        Debt.objects.filter(
            user=request.user, debt_type="payable", is_settled=False
        ).aggregate(Sum("remaining_amount"))["remaining_amount__sum"]
        or 0
    )

    # --- 3. Chart Generation ---
    pie_chart_div = None
    bar_chart_div = None
    if expenses_qs.exists():
        # Convert queryset to list of dicts for Pandas
        data = list(expenses_qs.values("amount", "category__name", "date_spent"))
        df = pd.DataFrame(data)

        # Pie Chart: Spending by Category
        fig_pie = px.pie(
            df,
            values="amount",
            names="category__name",
            title="Spending by Category",
            hole=0.4,
            color_discrete_sequence=px.colors.sequential.RdBu,
        )
        fig_pie.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=350)
        pie_chart_div = plot(fig_pie, output_type="div")

        # Bar Chart: Daily Expense Trend
        # Group by date and sum the amounts
        daily_df = df.groupby("date_spent")["amount"].sum().reset_index()
        daily_df = daily_df.sort_values("date_spent")  # Ensure chronological order

        fig_bar = px.bar(
            daily_df,
            x="date_spent",
            y="amount",
            title="Daily Expense Trend",
            labels={"date_spent": "Date", "amount": "NPR"},
        )
        fig_bar.update_traces(marker_color="#dc3545")  # Match the danger/red theme
        fig_bar.update_layout(margin=dict(t=40, b=0, l=0, r=0), height=350)
        bar_chart_div = plot(fig_bar, output_type="div")

    context = {
        "expenses": expenses_qs,
        "total_cash": total_balance,
        "total_receivable": to_receive,
        "total_payable": to_pay,
        "net_worth": (total_balance + to_receive) - to_pay,
        "categories": Category.objects.filter(
            user=request.user, category_type="expense"
        ),
        "accounts": Account.objects.filter(user=request.user),
        "pie_chart": pie_chart_div,
        "bar_chart": bar_chart_div,
    }
    return render(request, "expenses/expense_list.html", context)


@login_required
def add_expense(request):
    if request.method == "POST":
        try:
            with transaction.atomic():
                amount = Decimal(request.POST.get("amount", 0))
                account = get_object_or_404(
                    Account, id=request.POST.get("account"), user=request.user
                )
                category = get_object_or_404(
                    Category, id=request.POST.get("category"), user=request.user
                )

                Expense.objects.create(
                    user=request.user,
                    account=account,
                    category=category,
                    title=request.POST.get("title"),
                    amount=amount,
                    date_spent=request.POST.get("date_spent"),
                    tags=request.POST.get("tags"),
                    notes=request.POST.get("notes"),
                    is_recurring=request.POST.get("is_recurring") == "on",
                    recurring_interval=request.POST.get("recurring_interval", "none"),
                )
                messages.success(request, "Expense added successfully!")
                return redirect("expense_list")
        except ValidationError as e:
            # Handle "Insufficient Funds" or other logic errors
            messages.error(request, str(e).strip("[]'"))
        except ValueError:
            messages.error(request, "Please enter a valid number for the amount.")
        except Exception as e:
            messages.error(request, f"An error occurred: {str(e)}")

    return render(
        request,
        "expenses/expense_form.html",
        {
            "categories": Category.objects.filter(
                user=request.user, category_type="expense"
            ),
            "accounts": Account.objects.filter(user=request.user, is_active=True),
            "today_date": date.today().strftime("%Y-%m-%d"),
            "title": "Add Expense",
        },
    )


@login_required
def edit_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)

    if request.method == "POST":
        try:
            with transaction.atomic():
                new_amount = float(request.POST.get("amount"))
                old_amount = float(expense.amount)

                # Update logic: adjust balance by the difference
                if new_amount > old_amount:
                    expense.account.withdraw(new_amount - old_amount)
                elif new_amount < old_amount:
                    expense.account.deposit(old_amount - new_amount)

                expense.title = request.POST.get("title")
                expense.amount = new_amount
                category_id = request.POST.get("category")
                expense.category = get_object_or_404(
                    Category, id=category_id, user=request.user
                )
                expense.date_spent = request.POST.get("date_spent")
                expense.tags = request.POST.get("tags")
                expense.notes = request.POST.get("notes")
                expense.is_recurring = request.POST.get("is_recurring") == "on"
                expense.recurring_interval = (
                    request.POST.get("recurring_interval")
                    if expense.is_recurring
                    else "none"
                )

                expense.save()
                messages.success(request, "Expense updated and balance adjusted!")
                return redirect("expense_list")
        except ValidationError as e:
            messages.error(request, str(e))

    return render(
        request,
        "expenses/expense_form.html",
        {
            "expense": expense,
            "categories": Category.objects.filter(
                user=request.user, category_type="expense"
            ),
            "accounts": Account.objects.filter(user=request.user),
            "title": "Edit Expense",
            "today_date": date.today().strftime("%Y-%m-%d"),
        },
    )


@login_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk, user=request.user)
    if request.method == "POST":
        with transaction.atomic():
            expense.account.deposit(expense.amount)
            expense.is_active = False
            expense.save()
            messages.success(request, "Expense removed and amount refunded to account.")
            return redirect("expense_list")

    return render(request, "expenses/expense_confirm_delete.html", {"expense": expense})

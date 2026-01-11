from decimal import Decimal

import pandas as pd
import plotly.express as px
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404, redirect, render
from plotly.offline import plot

from .forms import AccountForm
from .models import Account, Contact, Debt, DebtPayment, Transfer


@login_required
def accounts_dashboard(request):
    user = request.user

    # --- 1. HANDLE POST REQUESTS (Create/Transfer) ---
    if request.method == "POST":
        action = request.POST.get("action")

        try:
            with transaction.atomic():
                if action == "create_account":
                    Account.objects.create(
                        user=user,
                        name=request.POST.get("name"),
                        account_type=request.POST.get("account_type"),
                        balance=Decimal(request.POST.get("balance") or 0),
                    )
                    messages.success(request, "Account created successfully.")

                elif action == "transfer_money":
                    from_acc = get_object_or_404(
                        Account, id=request.POST.get("from_account"), user=user
                    )
                    to_acc = get_object_or_404(
                        Account, id=request.POST.get("to_account"), user=user
                    )
                    amount = Decimal(request.POST.get("amount") or 0)

                    if from_acc == to_acc:
                        messages.error(request, "Cannot transfer to the same account.")
                    else:
                        Transfer.objects.create(
                            user=user,
                            from_account=from_acc,
                            to_account=to_acc,
                            amount=amount,
                        )
                        messages.success(
                            request, f"Transferred NPR {amount} successfully."
                        )
            return redirect("accounts_dashboard")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")

    # --- 2. METRICS & DATA ---
    accounts = Account.objects.filter(user=user, is_active=True).order_by("-balance")
    total_balance = accounts.aggregate(Sum("balance"))["balance__sum"] or Decimal(0)

    # Debt Metrics
    receivables = Debt.objects.filter(
        user=user, debt_type="receivable", is_settled=False
    ).aggregate(Sum("remaining_amount"))["remaining_amount__sum"] or Decimal(0)
    payables = Debt.objects.filter(
        user=user, debt_type="payable", is_settled=False
    ).aggregate(Sum("remaining_amount"))["remaining_amount__sum"] or Decimal(0)
    net_worth = (total_balance + receivables) - payables

    # --- 3. CHART: BALANCE DISTRIBUTION ---
    chart_wealth = ""
    if accounts.exists():
        df = pd.DataFrame(list(accounts.values("name", "balance")))
        df["balance"] = df["balance"].astype(float)
        df = df[df["balance"] > 0]  # Only plot accounts with money

        if not df.empty:
            fig = px.pie(
                df,
                values="balance",
                names="name",
                hole=0.5,
                color_discrete_sequence=px.colors.qualitative.Pastel,
            )
            fig.update_layout(
                showlegend=True,
                legend=dict(
                    orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5
                ),
                margin=dict(t=0, b=0, l=0, r=0),
                height=300,
            )
            chart_wealth = plot(fig, output_type="div", include_plotlyjs=True)

    context = {
        "accounts": accounts,
        "total_balance": total_balance,
        "receivables": receivables,
        "payables": payables,
        "net_worth": net_worth,
        "chart_wealth": chart_wealth,
        "recent_transfers": Transfer.objects.filter(user=user).order_by("-timestamp")[
            :5
        ],
        "account_types": Account.TYPE_CHOICES,
    }
    return render(request, "accounts/accounts_dashboard.html", context)


@login_required
def account_create(request):
    if request.method == "POST":
        form = AccountForm(request.POST)
        if form.is_valid():
            account = form.save(commit=False)
            account.user = request.user
            account.save()
            return redirect("account_list")
    else:
        form = AccountForm()
    return render(request, "accounts/account_form.html", {"form": form})


@login_required
def account_edit(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    if request.method == "POST":
        form = AccountForm(request.POST, instance=account)
        if form.is_valid():
            form.save()
            return redirect("account_list")
    else:
        form = AccountForm(instance=account)
    return render(request, "accounts/account_form.html", {"form": form})


@login_required
def account_delete(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    if request.method == "POST":
        account.is_active = False
        account.save()
        return redirect("account_list")
    return render(request, "accounts/account_confirm_delete.html", {"account": account})


@login_required
def account_detail(request, pk):
    account = get_object_or_404(Account, pk=pk, user=request.user)
    return render(request, "accounts/account_detail.html", {"account": account})


@login_required
def process_transfer(request):
    if request.method == "POST":
        from_id = request.POST.get("from_account")
        to_id = request.POST.get("to_account")
        amount = request.POST.get("amount")

        if from_id == to_id:
            # Add error message here
            messages.error(request, "Cannot transfer to the same account.")
            return redirect("accounts_dashboard")

        Transfer.objects.create(
            user=request.user,
            from_account_id=from_id,
            to_account_id=to_id,
            amount=amount,
        )
        messages.success(request, "Transfer completed successfully.")
        return redirect("accounts_dashboard")


@login_required
def debt_dashboard(request):
    user = request.user

    if request.method == "POST":
        action = request.POST.get("action")
        try:
            with transaction.atomic():
                if action == "add_contact":
                    Contact.objects.create(
                        user=user,
                        name=request.POST.get("name"),
                        phone=request.POST.get("phone", ""),
                    )
                    messages.success(request, "Contact added.")

                elif action == "add_debt":
                    # Initial Debt Creation (Borrow or Lend)
                    Debt.objects.create(
                        user=user,
                        contact_id=request.POST.get("contact"),
                        account_id=request.POST.get("account"),
                        initial_amount=Decimal(request.POST.get("amount")),
                        debt_type=request.POST.get("debt_type"),
                        is_settled=False,
                    )
                    messages.success(
                        request, "Debt record created and account balance updated."
                    )

                elif action == "make_payment":
                    # Reducing an existing Debt
                    debt_obj = get_object_or_404(
                        Debt, id=request.POST.get("debt_id"), user=user
                    )
                    DebtPayment.objects.create(
                        debt=debt_obj,
                        account_id=request.POST.get("account"),
                        amount_paid=Decimal(request.POST.get("amount")),
                    )
                    messages.success(request, "Payment recorded successfully.")

            return redirect("debt_page")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
    status_filter = request.GET.get("status", "active")
    debt_qs = Debt.objects.filter(user=user).select_related("contact", "account")

    if status_filter == "active":
        debt_qs = debt_qs.filter(is_settled=False)
    elif status_filter == "settled":
        debt_qs = debt_qs.filter(is_settled=True)
    elif status_filter == "partial":
        # Partial means it's not settled but some payment has been made
        debt_qs = debt_qs.filter(is_settled=False).exclude(
            remaining_amount=F("initial_amount"),
        )

    all_active = Debt.objects.filter(user=user, is_settled=False)
    total_receivable = (
        all_active.filter(debt_type="receivable").aggregate(Sum("remaining_amount"))[
            "remaining_amount__sum"
        ]
        or 0
    )
    total_payable = (
        all_active.filter(debt_type="payable").aggregate(Sum("remaining_amount"))[
            "remaining_amount__sum"
        ]
        or 0
    )

    context = {
        "contacts": Contact.objects.filter(user=user),
        "accounts": Account.objects.filter(user=user, is_active=True),
        "debts": debt_qs,  # This is the filtered list
        "total_receivable": total_receivable,
        "total_payable": total_payable,
        "current_status": status_filter,
    }
    return render(request, "accounts/debt_page.html", context)

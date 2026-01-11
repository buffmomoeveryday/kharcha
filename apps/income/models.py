from django.db import models
from django.contrib.auth.models import User
from apps.dashboard.models import Category
from apps.expenses.models import Expense
from apps.accounts.models import Account


class Income(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    source = models.CharField(max_length=100)  # e.g., "Salary", "Freelance"

    # Link to Account (e.g., Cash, Bank, eSewa)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="incomes"
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={"category_type": "income"},
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="NPR")
    date_received = models.DateField()

    is_recurring = models.BooleanField(default=False)
    recurring_interval = models.CharField(
        max_length=20,
        choices=Expense.RECURRING_INTERVALS,
        default="none",
    )

    tags = models.CharField(max_length=200, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.source} - {self.amount}"

    @property
    def transaction_date(self):
        return self.date_received

    def save(self, *args, **kwargs):
        if not self.pk:
            self.account.deposit(self.amount)
        super().save(*args, **kwargs)

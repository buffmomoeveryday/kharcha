from django.db import models
from django.contrib.auth.models import User

from apps.dashboard.models import Category
from apps.accounts.models import Account
from django.db import transaction


class Expense(models.Model):
    RECURRING_INTERVALS = [
        ("none", "None"),
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="expenses"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        limit_choices_to={"category_type": "expense"},
    )
    title = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date_spent = models.DateField()

    # Restored original fields
    is_recurring = models.BooleanField(default=False)
    recurring_interval = models.CharField(
        max_length=20, choices=RECURRING_INTERVALS, default="none"
    )
    tags = models.CharField(max_length=200, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                self.account.withdraw(self.amount)
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} - {self.amount}"

    @property
    def transaction_date(self):
        return self.date_spent

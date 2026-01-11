from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction  # noqa: D100

from apps.dashboard.models import Category


# --- 1. Account Model ---
class Account(models.Model):
    TYPE_CHOICES = [
        ("savings", "Savings"),
        ("checking", "Checking"),
        ("credit", "Credit Card"),
        ("cash", "Cash"),
        ("e-wallet", "E-Wallet"),
        ("other", "Other"),
    ]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    currency = models.CharField(max_length=10, default="NPR")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "name")

    def __str__(self):
        return f"{self.name} - {self.balance}"

    def deposit(self, amount):
        self.balance += Decimal(str(amount))
        self.save()

    def withdraw(self, amount):
        de_balance = Decimal(str(self.balance))
        de_amount = Decimal(str(amount))
        if de_balance < de_amount:
            raise ValidationError(f"Insufficient funds in {self.name}.")

        de_balance -= de_amount
        self.balance = de_balance
        self.save()


class Contact(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.name


class Transaction(models.Model):
    TRANSACTION_TYPES = [("income", "Income"), ("expense", "Expense")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    description = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # We use transaction.atomic so if balance update fails, the record isn't created
        with transaction.atomic():
            if not self.pk:  # Execute only on new creation
                if self.type == "income":
                    self.account.deposit(self.amount)
                else:
                    self.account.withdraw(self.amount)
            super().save(*args, **kwargs)


class Transfer(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    from_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transfers_out"
    )
    to_account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="transfers_in"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    timestamp = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                self.from_account.withdraw(self.amount)
                self.to_account.deposit(self.amount)
            super().save(*args, **kwargs)


class Debt(models.Model):
    DEBT_TYPE = [
        ("payable", "I owe them (Debt)"),
        ("receivable", "They owe me (Credit)"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    contact = models.ForeignKey(Contact, on_delete=models.CASCADE)
    initial_amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2)
    debt_type = models.CharField(max_length=20, choices=DEBT_TYPE)
    # The account used for the initial lending/borrowing transaction
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    is_settled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                self.remaining_amount = self.initial_amount
                # If I borrow (payable), my cash goes UP
                if self.debt_type == "payable":
                    self.account.deposit(self.initial_amount)
                # If I lend (receivable), my cash goes DOWN
                else:
                    self.account.withdraw(self.initial_amount)
            super().save(*args, **kwargs)


class DebtPayment(models.Model):
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="payments")
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if self.amount_paid > self.debt.remaining_amount:
                raise ValidationError("Payment amount exceeds remaining debt balance.")

            # Update Debt status
            self.debt.remaining_amount -= self.amount_paid
            if self.debt.remaining_amount == 0:
                self.debt.is_settled = True
            self.debt.save()

            # Update Account balance
            if self.debt.debt_type == "payable":
                # I am paying back a debt (Money OUT)
                self.account.withdraw(self.amount_paid)
            else:
                # I am receiving money owed to me (Money IN)
                self.account.deposit(self.amount_paid)

            super().save(*args, **kwargs)

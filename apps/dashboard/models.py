from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    CATEGORY_TYPES = [
        ("expense", "Expense"),
        ("income", "Income"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="categories")
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True, null=True)
    category_type = models.CharField(
        max_length=10, choices=CATEGORY_TYPES, default="expense"
    )

    # Budgeting fields
    budget_limit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[
            MinValueValidator(0),
        ],
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = "Categories"
        # Prevents a user from having two 'Food' categories for expenses
        unique_together = ("user", "name", "category_type")

    def get_category_type_display(self):
        return dict(self.CATEGORY_TYPES).get(self.category_type, "Unknown")

    def __str__(self):
        return f"{self.name} ({self.get_category_type_display()})"

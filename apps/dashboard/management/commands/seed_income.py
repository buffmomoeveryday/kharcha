import random
from datetime import timedelta
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.models import User
from income.models import Income
from dashboard.models import Category
from accounts.models import Account


class Command(BaseCommand):
    help = "Seeds the database with sample income data for testing"

    def handle(self, *args, **options):
        # 1. Get or Create a test user
        user = User.objects.first()
        if not user:
            self.stdout.write(
                self.style.ERROR("No user found. Please create a superuser first.")
            )
            return

        # 2. Get or Create an Account
        account, _ = Account.objects.get_or_create(
            user=user,
            name="Main Bank Account",
            defaults={"balance": 50000, "account_type": "bank"},
        )

        # 3. Get or Create Income Categories
        income_cats = ["Salary", "Freelancing", "Dividends", "Gifts", "Rental Income"]
        category_objs = []
        for cat_name in income_cats:
            obj, _ = Category.objects.get_or_create(
                user=user, name=cat_name, category_type="income"
            )
            category_objs.append(obj)

        # 4. Generate Data
        self.stdout.write("Seeding income data...")
        sources = [
            "Monthly Paycheck",
            "Upwork Project",
            "Stock Dividend",
            "Birthday Gift",
            "Apartment Rent",
        ]

        # Seed 30 random income entries over the last 90 days
        for i in range(30):
            random_days = random.randint(0, 90)
            date_received = timezone.now().date() - timedelta(days=random_days)

            # Use Decimal for financial precision
            amount = Decimal(random.randrange(500, 15000))

            Income.objects.create(
                user=user,
                source=random.choice(sources),
                account=account,
                category=random.choice(category_objs),
                amount=amount,
                date_received=date_received,
                notes="Automated seed data for testing charts.",
                is_active=True,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded 30 income records for {user.username}!"
            )
        )

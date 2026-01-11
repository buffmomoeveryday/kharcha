import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from expenses.models import Expense, Category
from accounts.models import Account


class Command(BaseCommand):
    help = "Seed database with sample Expense data using the first available user"

    def handle(self, *args, **kwargs):
        # 1. Get the first user
        user = User.objects.first()

        if not user:
            self.stdout.write(
                self.style.ERROR("No users found. Please create a user first.")
            )
            return

        self.stdout.write(self.style.SUCCESS(f"Seeding data for user: {user.username}"))

        # 2. Ensure an Account exists with enough balance
        account, _ = Account.objects.get_or_create(
            user=user,
            name="Main Cash",
            defaults={
                "account_type": "cash",
                "balance": 150000.00,  # High balance to ensure seed doesn't fail
                "currency": "NPR",
            },
        )

        # 3. Setup Categories
        expense_cats = [
            "Food",
            "Transport",
            "Shopping",
            "Entertainment",
            "Bills",
            "Health",
        ]
        expense_cat_objs = []
        for name in expense_cats:
            cat, _ = Category.objects.get_or_create(
                user=user, name=name, category_type="expense"
            )
            expense_cat_objs.append(cat)

        # 4. Data Options
        expense_titles = [
            "Groceries",
            "Taxi Fare",
            "Internet Bill",
            "Dinner Out",
            "Movie Tickets",
            "Pharmacy",
            "Gym Membership",
        ]
        intervals = ["none", "none", "none", "monthly"]

        # Start Date (90 days ago)
        start_date = datetime.now() - timedelta(days=90)

        self.stdout.write("Seeding expenses...")

        # 5. Create 50 Expense records
        created_count = 0
        for i in range(50):
            current_date = (start_date + timedelta(days=random.randint(1, 90))).date()
            amount = random.randint(150, 4500)

            try:
                # Removed 'payment_method' as it's no longer in your model
                Expense.objects.create(
                    user=user,
                    account=account,
                    category=random.choice(expense_cat_objs),
                    title=random.choice(expense_titles),
                    amount=amount,
                    date_spent=current_date,
                    is_recurring=random.choice([True, False]),
                    recurring_interval=random.choice(intervals),
                    notes="Automated seed data",
                    is_active=True,
                )
                created_count += 1
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"Skipped an expense: {e}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully seeded {created_count} expenses to account '{account.name}'!"
            )
        )

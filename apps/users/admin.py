from django.contrib import admin
from apps.income.models import Income
from apps.expenses.models import Expense
# Register your models here.


admin.site.register(Income)
admin.site.register(Expense)

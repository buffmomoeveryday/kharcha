from django.forms import ModelForm


class AccountForm(ModelForm):
    class Meta:
        from .models import Account

        model = Account
        fields = ["name", "account_type", "balance", "currency", "is_active"]

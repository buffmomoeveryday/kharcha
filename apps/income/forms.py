from django import forms
from .models import Income


class IncomeForm(forms.ModelForm):
    class Meta:
        model = Income
        fields = [
            "source",
            "amount",
            "category",
            "date_received",
            "is_recurring",
            "recurring_interval",
        ]
        widgets = {
            "date_received": forms.DateInput(
                attrs={"type": "date", "class": "form-control"}
            ),
            "source": forms.TextInput(
                attrs={
                    "placeholder": "Salary, Freelance, etc.",
                    "class": "form-control",
                }
            ),
            "amount": forms.NumberInput(attrs={"class": "form-control"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "recurring_interval": forms.Select(attrs={"class": "form-control"}),
        }

    def clean_amount(self):
        print("he")
        amount = self.cleaned_data.get("amount")
        if amount <= 0:
            raise forms.ValidationError("Amount must be greater than zero.")
        return amount

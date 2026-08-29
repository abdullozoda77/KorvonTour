from django import forms
from .models import Category, Product, Expense, Country
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'description']
    
class CountryForm(forms.ModelForm):
    class Meta:
        model = Country
        fields = [
            'country_name',
            'shop',
            'phone',
            'address',
            'description',
        ]

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name',
            'photo',
            'unique_code',
            'xarid',
            'furush',
            'quantity',
            'description',
            'category',
            'country',
        ]

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            'expense_type',
            'name',
            'price',
            'quantity',
            'date',
            'description',
        ]

    def clean(self):
        cleaned_data = super().clean()
        expense_type = cleaned_data.get('expense_type')
        if expense_type and expense_type != 'products':
            cleaned_data['quantity'] = None
        return cleaned_data
    
class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from .models import Category, Product, Country, Expense, User
from .forms import CategoryForm, ProductForm, CountryForm, ExpenseForm, RegisterForm
from django.contrib.auth.models import Group
from functools import wraps
from django.core.exceptions import PermissionDenied

def viewer_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.groups.filter(name='Viewer').exists():
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapper

def home(request):
    products = Product.objects.all()
    categories = Category.objects.all()
    expenses = Expense.objects.all()
    total_expenses = sum(expense.total for expense in expenses)
    context = {
        'products': products,
        'categories': categories,
        'expenses': expenses,
        'total_expenses': total_expenses,
    }

    return render(request, 'home.html', context)

def category_list(request):
    category = Category.objects.all()
    return render(request, 'category/category_list.html', {'category': category})

def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    products = category.products.all()
    if not request.user.is_superuser:
        products = products.filter(user=request.user)
    return render(request, 'category/category_detail.html', {'category': category, 'products': products})

@viewer_required
def create_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('category_list')
    else:
        form = CategoryForm()
    return render(request, 'category/create_category.html', {'form': form})

@viewer_required
def update_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'category/update_category.html', {'form': form})

@viewer_required
def delete_category(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.delete()
        return redirect('category_list')
    return render(request, 'category/delete_category.html', {'category': category})

def country_list(request):
    country = Country.objects.all()
    return render(request, 'country/country_list.html', {'country': country})

def country_detail(request, pk):
    country = get_object_or_404(Country, pk=pk)
    products = country.products.all()
    return render(request, 'country/country_detail.html', {'country': country, 'products': products})

@viewer_required
def create_country(request):
    if request.method == 'POST':
        form = CountryForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect('country_list')
    else:
        form = CountryForm()
    return render(request, 'country/create_country.html', {'form': form})

@viewer_required
def update_country(request, pk):
    country = get_object_or_404(Country, pk=pk)
    if request.method == 'POST':
        form = CountryForm(request.POST, instance=country)
        if form.is_valid():
            form.save()
            return redirect('country_list')
    else:
        form = CountryForm(instance=country)
    return render(request, 'country/update_country.html', {'form': form})

@viewer_required
def delete_country(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    country = get_object_or_404(Country, pk=pk)
    if request.method == 'POST':
        country.delete()
        return redirect('country_list')
    return render(request, 'country/delete_country.html', {'country': country})

def purchase_list(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    purchases = Product.objects.all()
    total_spent = sum(p.xarid * p.quantity for p in purchases)
    total_qty = sum(p.quantity for p in purchases)
    return render(request, 'purchase/purchase_list.html', {
        'purchases': purchases,
        'total_spent': total_spent,
        'total_qty': total_qty,
    })

def employees_list(request):
    if not request.user.is_superuser:
        raise PermissionDenied
    suppliers = Country.objects.all()
    return render(request, 'employees/employees_list.html', {'suppliers': suppliers})

def product_list(request):
    products = Product.objects.all()
    if not request.user.is_superuser:
        products = products.filter(user=request.user)
    return render(request,'product/product_list.html',{'product': products})

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.is_superuser and product.user != request.user:
        raise PermissionDenied
    return render(request, 'product/product_detail.html', {'product': product})

@viewer_required
def create_product(request):
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES)

        if form.is_valid():
            product = form.save(commit=False)
            product.user = request.user
            product.save()

            Expense.objects.create(
                expense_type='products',
                name=f'Хариди {product.name}',
                price=product.xarid,
                quantity=product.quantity,
                date=product.created_at.date(),
                description=f'Хариди {product.quantity} дона {product.name}',
                product=product,
                user=request.user,
            )

            return redirect('product_list')

    else:
        form = ProductForm()

    return render(
        request,
        'product/create_product.html',
        {'form': form}
    )

@viewer_required
def update_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.is_superuser and product.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()

            expense = product.expenses.filter(expense_type='products').first()
            if expense:
                expense.name = f'Хариди {product.name}'
                expense.price = product.xarid
                expense.quantity = product.quantity
                expense.description = f'Хариди {product.quantity} дона {product.name}'
                expense.save()

            return redirect('product_list')
    else:
        form = ProductForm(instance=product)
    return render(request, 'product/update_product.html', {'form': form})

@viewer_required
def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.is_superuser and product.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        product.delete()
        return redirect('product_list')
    return render(request, 'product/delete_product.html', {'product': product})

def expense_list(request):
    expenses = Expense.objects.all()
    if not request.user.is_superuser:
        expenses = expenses.filter(user=request.user)
    total_expenses = sum(expense.total for expense in expenses)
    return render(request,'expense/expense_list.html',{'expense': expenses,'total_expenses': total_expenses,})

def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_superuser and expense.user != request.user:
        raise PermissionDenied
    return render(request, 'expense/expense_detail.html', {'expense': expense})

@viewer_required
def create_expense(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)

        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()
            return redirect('expense_list')
    else:
        form = ExpenseForm()
    return render(request, 'expense/create_expense.html', {'form': form})

@viewer_required
def update_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_superuser and expense.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            return redirect('expense_list')
    else:
        form = ExpenseForm(instance=expense)
    return render(request, 'expense/update_expense.html', {'form': form})

@viewer_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_superuser and expense.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        expense.delete()
        return redirect('expense_list')
    return render(request, 'expense/delete_expense.html', {'expense': expense})

def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            group = Group.objects.get(name='User')
            user.groups.add(group)
            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})

def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Неверное имя пользователя или пароль')

    return render(request, 'accounts/login.html')

def user_logout(request):
    logout(request)
    return redirect('login')


def settings(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        messages.success(request, 'Настройки сохранены')
        return redirect('settings')
    return render(request, 'settings/settings.html')
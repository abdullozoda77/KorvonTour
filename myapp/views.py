from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from .models import Category, Product, Country, Sklad, Expense, User, Profile
from .forms import CategoryForm, ProductForm, CountryForm, SkladForm, ExpenseForm, RegisterForm, ProfileForm
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.http import JsonResponse

NOTIFICATION_LIMIT = 10

NOTIFICATION_ICONS = {
    'Товар': '📦',
    'Расход': '💸',
    'Категория': '🗂️',
    'Поставщик': '🌍',
    'Склад': '🏬',
}

def notifications(request):
    data = {'notifications': []}
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return data

    last_seen = None
    if hasattr(request.user, 'profile'):
        last_seen = request.user.profile.last_notifications_seen

    def since(qs):
        if last_seen:
            return qs.filter(created_at__gt=last_seen)
        return qs

    if request.user.is_superuser:
        products = since(Product.objects.all())
        expenses = since(Expense.objects.all())
        categories = since(Category.objects.all())
        countries = since(Country.objects.all())
        sklads = since(Sklad.objects.all())
    else:
        products = since(Product.objects.filter(user=request.user))
        expenses = since(Expense.objects.filter(user=request.user))
        categories = since(Category.objects.filter(user=request.user))
        countries = since(Country.objects.filter(user=request.user))
        sklads = since(Sklad.objects.filter(user=request.user))

    items = []
    for p in products.select_related('user'):
        items.append({'ts': p.created_at, 'type': 'Товар', 'name': p.name,
                      'owner': p.user.username if p.user else None})
    for e in expenses.select_related('user'):
        items.append({'ts': e.created_at, 'type': 'Расход', 'name': e.name,
                      'owner': e.user.username if e.user else None})
    for c in categories.select_related('user'):
        items.append({'ts': c.created_at, 'type': 'Категория', 'name': c.name,
                      'owner': c.user.username if c.user else None})
    for c in countries.select_related('user'):
        items.append({'ts': c.created_at, 'type': 'Поставщик', 'name': c.country_name,
                      'owner': c.user.username if c.user else None})
    for s in sklads.select_related('user'):
        items.append({'ts': s.created_at, 'type': 'Склад', 'name': s.name,
                      'owner': s.user.username if s.user else None})

    items.sort(key=lambda x: x['ts'] or timezone.now(), reverse=True)
    items = items[:NOTIFICATION_LIMIT]
    for it in items:
        it['icon'] = NOTIFICATION_ICONS.get(it['type'], '🔔')
    data['notifications'] = items
    return data

@require_POST
def mark_notifications_seen(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.last_notifications_seen = timezone.now()
    profile.save(update_fields=['last_notifications_seen'])
    return JsonResponse({'ok': True})

def home(request):
    if request.user.is_superuser or not request.user.is_authenticated:
        products = Product.objects.all()
        categories = Category.objects.all()
        expenses = Expense.objects.all()
    else:
        products = Product.objects.filter(user=request.user)
        categories = Category.objects.filter(user=request.user)
        expenses = Expense.objects.filter(user=request.user)
    total_expenses = sum(expense.total for expense in expenses)
    total_stock = sum(product.quantity for product in products)
    total_purchase = sum((p.xarid or 0) * p.quantity for p in products)
    total_sale = sum((p.furush or 0) * p.quantity for p in products)

    home_users = []
    if request.user.is_superuser:
        for u in User.objects.filter(is_superuser=False).order_by('username'):
            ps = Product.objects.filter(user=u)
            spent = sum((p.xarid or 0) * p.quantity for p in ps)
            if spent:
                home_users.append({
                    'name': u.get_full_name() or u.username,
                    'spent': spent,
                })

    if request.user.is_superuser:
        skladi = Sklad.objects.all().order_by('name', 'id')
    elif request.user.is_authenticated:
        skladi = Sklad.objects.filter(user=request.user).order_by('name', 'id')
    else:
        skladi = Sklad.objects.none()

    city_groups = []
    by_city = {}
    for s in skladi.select_related('user'):
        key = s.city or s.name or 'Без города'
        g = by_city.setdefault(key, {
            'city': key,
            'map_x': s.map_x,
            'map_y': s.map_y,
            'lat': s.lat,
            'lng': s.lng,
            'sklads': [],
        })
        if not g['map_x'] and not g['map_y']:
            g['map_x'] = s.map_x
            g['map_y'] = s.map_y
            g['lat'] = s.lat
            g['lng'] = s.lng
        g['sklads'].append({
            'user': s.user.username if s.user else s.name,
            'name': s.name,
            'address': s.address,
            'phone': s.phone,
            'lat': s.lat,
            'lng': s.lng,
        })
    for key in by_city:
        city_groups.append(by_city[key])
    city_groups.sort(key=lambda g: g['city'])

    context = {
        'products': products,
        'categories': categories,
        'expenses': expenses,
        'total_expenses': total_expenses,
        'total_stock': total_stock,
        'total_purchase': total_purchase,
        'total_sale': total_sale,
        'home_users': home_users,
        'skladi': skladi,
        'city_groups': city_groups,
    }

    return render(request, 'home.html', context)

def category_list(request):
    category = Category.objects.all()
    if not request.user.is_superuser:
        if request.user.is_authenticated:
            category = category.filter(user=request.user)
        else:
            category = category.none()
    return render(request, 'category/category_list.html', {'category': category, })

def category_detail(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if not request.user.is_superuser and category.user != request.user:
        raise PermissionDenied
    products = category.products.all()
    if not request.user.is_superuser:
        products = products.filter(user=request.user)
    return render(request, 'category/category_detail.html', {'category': category, 'products': products, })

def create_category(request):
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        form.instance.user = request.user

        if form.is_valid():
            category = form.save(commit=False)
            category.user = request.user
            category.save()
            return redirect('category_list')
    else:
        form = CategoryForm()
    return render(request, 'category/create_category.html', {'form': form, })

def update_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if not request.user.is_superuser and category.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = CategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            return redirect('category_list')
    else:
        form = CategoryForm(instance=category)
    return render(request, 'category/update_category.html', {'form': form, })

def delete_category(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if not request.user.is_superuser and category.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        category.delete()
        return redirect('category_list')
    return render(request, 'category/delete_category.html', {'category': category, })

def country_list(request):
    country = Country.objects.all()
    if not request.user.is_superuser:
        if request.user.is_authenticated:
            country = country.filter(user=request.user)
        else:
            country = country.none()
    return render(request, 'country/country_list.html', {'country': country, })

def country_detail(request, pk):
    country = get_object_or_404(Country, pk=pk)
    if not request.user.is_superuser and country.user != request.user:
        raise PermissionDenied
    products = country.products.all()
    return render(request, 'country/country_detail.html', {'country': country, 'products': products, })

def create_country(request):
    if request.method == 'POST':
        form = CountryForm(request.POST)

        if form.is_valid():
            country = form.save(commit=False)
            country.user = request.user
            country.save()
            return redirect('country_list')
    else:
        form = CountryForm()
    return render(request, 'country/create_country.html', {'form': form, })

def update_country(request, pk):
    country = get_object_or_404(Country, pk=pk)
    if not request.user.is_superuser and country.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = CountryForm(request.POST, instance=country)
        if form.is_valid():
            form.save()
            return redirect('country_list')
    else:
        form = CountryForm(instance=country)
    return render(request, 'country/update_country.html', {'form': form, })

def delete_country(request, pk):
    country = get_object_or_404(Country, pk=pk)
    if not request.user.is_superuser and country.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        country.delete()
        return redirect('country_list')
    return render(request, 'country/delete_country.html', {'country': country, })

def sklad_list(request):
    if request.user.is_superuser:
        skladi = Sklad.objects.all().select_related('user').order_by('name', 'id')
    elif request.user.is_authenticated:
        skladi = Sklad.objects.filter(user=request.user).select_related('user').order_by('name', 'id')
    else:
        skladi = Sklad.objects.none()
    return render(request, 'sklad/sklad_list.html', {'skladi': skladi})

def create_sklad(request):
    if not request.user.is_authenticated:
        raise PermissionDenied
    if request.method == 'POST':
        form = SkladForm(request.POST)
        if form.is_valid():
            sklad = form.save(commit=False)
            sklad.set_city_coords()
            if not request.user.is_superuser:
                sklad.user = request.user
            sklad.save()
            return redirect('sklad_list')
    else:
        form = SkladForm()
        if not request.user.is_superuser:
            form.fields.pop('user')
    return render(request, 'sklad/create_sklad.html', {'form': form, })

def update_sklad(request, pk):
    sklad = get_object_or_404(Sklad, pk=pk)
    if not request.user.is_superuser and sklad.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        form = SkladForm(request.POST, instance=sklad)
        form.fields.pop('user')
        if form.is_valid():
            sklad = form.save(commit=False)
            sklad.set_city_coords()
            sklad.save()
            return redirect('sklad_list')
    else:
        form = SkladForm(instance=sklad)
        form.fields.pop('user')
    return render(request, 'sklad/update_sklad.html', {'form': form, 'sklad': sklad})

def delete_sklad(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied
    sklad = get_object_or_404(Sklad, pk=pk)
    if request.method == 'POST':
        sklad.delete()
        return redirect('sklad_list')
    return render(request, 'sklad/delete_sklad.html', {'sklad': sklad})

def purchase_list(request):
    purchases = Product.objects.all()
    total_spent = sum(p.xarid * p.quantity for p in purchases)
    total_qty = sum(p.quantity for p in purchases)
    return render(request, 'purchase/purchase_list.html', {
        'purchases': purchases,
        'total_spent': total_spent,
        'total_qty': total_qty,
           })

def employees_list(request):
    suppliers = Country.objects.all()
    if not request.user.is_superuser:
        if request.user.is_authenticated:
            suppliers = suppliers.filter(user=request.user)
        else:
            suppliers = suppliers.none()
    return render(request, 'employees/employees_list.html', {'suppliers': suppliers, })

def product_list(request):
    products = Product.objects.all()
    if not request.user.is_superuser:
        if request.user.is_authenticated:
            products = products.filter(user=request.user)
        else:
            products = products.none()
    return render(request,'product/product_list.html',{'product': products, })

def product_detail(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.is_superuser and product.user != request.user:
        raise PermissionDenied
    return render(request, 'product/product_detail.html', {'product': product, })
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

    if not request.user.is_superuser:
        form.fields['category'].queryset = Category.objects.filter(user=request.user)
        form.fields['country'].queryset = Country.objects.filter(user=request.user)

    return render(
        request,
        'product/create_product.html',
        {'form': form, }
    )

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
    if not request.user.is_superuser:
        form.fields['category'].queryset = Category.objects.filter(user=request.user)
        form.fields['country'].queryset = Country.objects.filter(user=request.user)
    return render(request, 'product/update_product.html', {'form': form, })

def delete_product(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if not request.user.is_superuser and product.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        product.delete()
        return redirect('product_list')
    return render(request, 'product/delete_product.html', {'product': product, })

def expense_list(request):
    expenses = Expense.objects.all()
    if not request.user.is_superuser:
        if request.user.is_authenticated:
            expenses = expenses.filter(user=request.user)
        else:
            expenses = expenses.none()
    total_expenses = sum(expense.total for expense in expenses)
    return render(request,'expense/expense_list.html',{'expense': expenses,'total_expenses': total_expenses,})

def expense_detail(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_superuser and expense.user != request.user:
        raise PermissionDenied
    return render(request, 'expense/expense_detail.html', {'expense': expense, })

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
    return render(request, 'expense/create_expense.html', {'form': form, })

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
    return render(request, 'expense/update_expense.html', {'form': form, })

def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if not request.user.is_superuser and expense.user != request.user:
        raise PermissionDenied
    if request.method == 'POST':
        expense.delete()
        return redirect('expense_list')
    return render(request, 'expense/delete_expense.html', {'expense': expense, })

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


def reports(request):
    if not request.user.is_authenticated:
        return redirect('login')

    rows = []
    total_count = 0
    total_qty = 0
    total_spent = 0

    def build(owner):
        ps = Product.objects.filter(user=owner)
        cnt = ps.count()
        qty = sum(p.quantity for p in ps)
        spent = sum((p.xarid or 0) * p.quantity for p in ps)
        return {
            'name': owner.get_full_name() or owner.username,
            'username': owner.username,
            'count': cnt,
            'qty': qty,
            'spent': spent,
        }

    if request.user.is_superuser:
        for u in User.objects.filter(is_superuser=False).order_by('username'):
            r = build(u)
            if r['count']:
                rows.append(r)
        rows.sort(key=lambda r: r['spent'], reverse=True)
    else:
        r = build(request.user)
        if r['count']:
            rows.append(r)

    for r in rows:
        total_count += r['count']
        total_qty += r['qty']
        total_spent += r['spent']

    return render(request, 'reports/reports.html', {
        'report_rows': rows,
        'total_count': total_count,
        'total_qty': total_qty,
        'total_spent': total_spent,
    })


def settings(request):
    if not request.user.is_authenticated:
        return redirect('login')
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.save()

        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()

        messages.success(request, 'Настройки сохранены')
        return redirect('settings')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'settings/settings.html', {'form': form, })
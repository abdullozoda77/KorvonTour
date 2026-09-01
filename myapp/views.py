import json
import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.core.exceptions import PermissionDenied
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.conf import settings as django_settings
from .models import Category, Product, Country, Sklad, Expense, User, Profile
from .forms import CategoryForm, ProductForm, CountryForm, SkladForm, ExpenseForm, RegisterForm, ProfileForm
from django.contrib.auth.models import Group
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db.models import Q

NOTIFICATION_LIMIT = 10
AI_CHAT_HISTORY_LIMIT = 40
AI_CHAT_CONTEXT_TURNS = 10
GEMINI_MODEL = 'gemini-3.5-flash-lite'
GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'

NOTIFICATION_ICONS = {
    'Товар': '📦',
    'Расход': '💸',
    'Категория': '🗂️',
    'Поставщик': '🌍',
    'Склад': '🏬',
}


def notifications(request):
    if not request.user.is_authenticated:
        return {'notifications': []}
    last_seen = getattr(getattr(request.user, 'profile', None), 'last_notifications_seen', None)
    if request.user.is_superuser:
        user_filter = {}
    else:
        user_filter = {'user': request.user}
    models = [
        (Product, 'Товар', 'name'),
        (Expense, 'Расход', 'name'),
        (Category, 'Категория', 'name'),
        (Country, 'Поставщик', 'country_name'),
        (Sklad, 'Склад', 'name'),
    ]
    items = []
    for model, type_name, name_field in models:
        objects = model.objects.filter(**user_filter)
        if last_seen:
            objects = objects.filter(created_at__gt=last_seen)
        for obj in objects.select_related('user'):
            items.append({
                'ts': obj.created_at,
                'type': type_name,
                'name': getattr(obj, name_field),
                'owner': obj.user.username if obj.user else None,
                'icon': NOTIFICATION_ICONS.get(type_name, '🔔'),
            })
    items.sort(key=lambda x: x['ts'], reverse=True)
    return {'notifications': items[:NOTIFICATION_LIMIT]}


def home_search(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'auth'}, status=401)
    if request.user.is_superuser:
        user_filter = {}
    else:
        user_filter = {'user': request.user}
    q = (request.GET.get('q') or '').strip()
    results = []
    if q:
        products = (
            Product.objects.filter(**user_filter)
            .select_related('category', 'country')
            .filter(Q(name__icontains=q) | Q(category__name__icontains=q))
            .order_by('name', 'id')
        )
        expenses = (
            Expense.objects.filter(**user_filter)
            .filter(Q(name__icontains=q) | Q(description__icontains=q))
            .order_by('-created_at')
        )
    else:
        products = (
            Product.objects.filter(**user_filter)
            .select_related('category', 'country')
            .order_by('name', 'id')
        )
        expenses = Expense.objects.filter(**user_filter).order_by('-created_at')

    for p in products[:50]:
        results.append({
            'type': 'product',
            'id': p.id,
            'name': p.name,
            'category': p.category.name if p.category else '',
            'quantity': p.quantity,
            'photo': p.photo.url if p.photo else None,
        })
    for e in expenses[:20]:
        results.append({
            'type': 'expense',
            'id': e.id,
            'name': e.name,
            'kind': e.get_expense_type_display(),
            'total': str(e.total),
            'date': e.date.strftime('%d.%m.%Y'),
        })
    return JsonResponse({'ok': True, 'q': q, 'results': results})


def build_ai_context(user):
    if user.is_superuser:
        products = Product.objects.select_related('category', 'user').all().order_by('name')
    else:
        products = Product.objects.select_related('category').filter(user=user).order_by('name')
    lines = []
    for p in products:
        owner = f', владелец: {p.user.username}' if user.is_superuser and p.user else ''
        category = p.category.name if p.category else 'без категории'
        lines.append(
            f'- {p.name}: {p.quantity} шт., категория: {category}, '
            f'закупка {p.xarid} сом/шт, продажа {p.furush} сом/шт{owner}'
        )
    if not lines:
        return 'Товаров пока нет.'
    return '\n'.join(lines)


def ai_chat(request):
    if not request.user.is_authenticated:
        return redirect('login')
    history = request.session.get('ai_chat_history', [])
    return render(request, 'ai/ai_chat.html', {'history': history})


@require_POST
def ai_chat_message(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False, 'error': 'auth'}, status=401)
    if not django_settings.GEMINI_API_KEY:
        return JsonResponse({'ok': False, 'error': 'no_api_key'}, status=503)
    try:
        payload = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({'ok': False, 'error': 'bad_request'}, status=400)
    message = (payload.get('message') or '').strip()
    if not message:
        return JsonResponse({'ok': False, 'error': 'empty'}, status=400)

    history = request.session.get('ai_chat_history', [])

    system_prompt = (
        'Ты — AI-ассистент склада Korvon Tour. Отвечай кратко и по делу, на русском языке. '
        'Используй только приведённые ниже данные о товарах, не выдумывай цифры и не добавляй товары, '
        'которых нет в списке.\n\nДанные о товарах:\n' + build_ai_context(request.user)
    )
    contents = [
        {'role': 'user', 'parts': [{'text': system_prompt}]},
        {'role': 'model', 'parts': [{'text': 'Понял, готов отвечать на вопросы о товарах.'}]},
    ]
    for turn in history[-AI_CHAT_CONTEXT_TURNS:]:
        contents.append({'role': turn['role'], 'parts': [{'text': turn['text']}]})
    contents.append({'role': 'user', 'parts': [{'text': message}]})

    try:
        resp = requests.post(
            GEMINI_URL,
            params={'key': django_settings.GEMINI_API_KEY},
            json={'contents': contents},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = data['candidates'][0]['content']['parts'][0]['text']
    except Exception:
        return JsonResponse({'ok': False, 'error': 'ai_failed'}, status=502)

    history.append({'role': 'user', 'text': message})
    history.append({'role': 'model', 'text': reply})
    request.session['ai_chat_history'] = history[-AI_CHAT_HISTORY_LIMIT:]

    return JsonResponse({'ok': True, 'reply': reply})

@require_POST
def ai_chat_reset(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    request.session['ai_chat_history'] = []
    return JsonResponse({'ok': True})


@require_POST
def mark_notifications_seen(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    profile, created = Profile.objects.get_or_create(user=request.user)
    profile.last_notifications_seen = timezone.now()
    profile.save()
    return JsonResponse({'ok': True})


def home(request):
    if not request.user.is_authenticated:
        return redirect('login')
    if request.user.is_superuser:
        user_filter = {}
    else:
        user_filter = {'user': request.user}
    products = Product.objects.filter(**user_filter)
    categories = Category.objects.filter(**user_filter)
    expenses = Expense.objects.filter(**user_filter)
    skladi = Sklad.objects.filter(**user_filter).order_by('name', 'id')
    total_expenses = sum(expense.total for expense in expenses)
    total_stock = sum(product.quantity for product in products)
    total_purchase = sum(
        (product.xarid or 0) * product.quantity
        for product in products
    )
    total_sale = sum(
        (product.furush or 0) * product.quantity
        for product in products
    )
    home_users = []
    if request.user.is_authenticated and request.user.is_superuser:
        for user in User.objects.filter(is_superuser=False).order_by('username'):
            products_user = Product.objects.filter(user=user)
            spent = sum(
                (product.xarid or 0) * product.quantity
                for product in products_user
            )
            if spent:
                home_users.append({
                    'name': user.get_full_name() or user.username,
                    'spent': spent,
                })
    by_city = {}
    for sklad in skladi.select_related('user'):
        city = sklad.city or sklad.name or 'Без города'
        if city not in by_city:
            by_city[city] = {
                'city': city,
                'map_x': sklad.map_x,
                'map_y': sklad.map_y,
                'lat': sklad.lat,
                'lng': sklad.lng,
                'sklads': [],
            }
        by_city[city]['sklads'].append({
            'user': sklad.user.username if sklad.user else sklad.name,
            'name': sklad.name,
            'address': sklad.address,
            'phone': sklad.phone,
            'lat': sklad.lat,
            'lng': sklad.lng,
        })
    city_groups = sorted(
        by_city.values(),
        key=lambda city: city['city']
    )
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
    return render(request, 'product/product_list.html', {'product': products, })

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
    return render(request, 'product/create_product.html', {'form': form, })

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
    return render(request, 'expense/expense_list.html', {'expense': expenses, 'total_expenses': total_expenses, })

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
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    image = models.ImageField(upload_to='profiles/', blank=True, null=True)
    last_notifications_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username

class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='categories', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'name'], name='unique_category_per_user', nulls_distinct=True),
        ]

    def __str__(self):
        return self.name
    
class Country(models.Model):
    country_name = models.CharField(max_length=100)
    shop = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    description = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='countries', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.country_name} - {self.shop}'

class Sklad(models.Model):
    CITY_COORDS = {
        'Душанбе': {'map_x': 217, 'map_y': 407, 'lat': 38.5598, 'lng': 68.7870},
        'Худжанд': {'map_x': 313, 'map_y': 147, 'lat': 40.2900, 'lng': 69.6220},
        'Курган-Тюбе': {'map_x': 216, 'map_y': 515, 'lat': 37.8365, 'lng': 68.7800},
        'Куляб': {'map_x': 331, 'map_y': 504, 'lat': 37.9146, 'lng': 69.7820},
        'Хорог': {'map_x': 535, 'map_y': 567, 'lat': 37.4910, 'lng': 71.5570},
        'РРП': {'map_x': 279, 'map_y': 362, 'lat': 38.8600, 'lng': 69.3300},
        'Истаравшан': {'map_x': 242, 'map_y': 204, 'lat': 39.9107, 'lng': 69.0068},
    }

    name = models.CharField(max_length=200, verbose_name='Название склада')
    city = models.CharField(max_length=100, blank=True, default='', verbose_name='Город')
    address = models.CharField(max_length=255, blank=True, default='', verbose_name='Адрес')
    phone = models.CharField(max_length=20, blank=True, default='', verbose_name='Телефон')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    map_x = models.IntegerField(default=0, blank=True, verbose_name='Позиция на карте (X)')
    map_y = models.IntegerField(default=0, blank=True, verbose_name='Позиция на карте (Y)')
    lat = models.FloatField(default=0, blank=True, verbose_name='Широта')
    lng = models.FloatField(default=0, blank=True, verbose_name='Долгота')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sklads', null=True, blank=True, verbose_name='Хозяин склада')
    created_at = models.DateTimeField(auto_now_add=True)

    def set_city_coords(self):
        coords = self.CITY_COORDS.get(self.city)
        if coords:
            self.map_x = coords['map_x']
            self.map_y = coords['map_y']
            self.lat = coords['lat']
            self.lng = coords['lng']

    def __str__(self):
        return self.name

class Product(models.Model):
    name = models.CharField(max_length=200)
    photo = models.ImageField(upload_to='products/', blank=True, null=True)
    unique_code = models.CharField(max_length=300, unique=True)
    xarid = models.DecimalField(max_digits=12, decimal_places=2)
    furush = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(default=0)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    country = models.ForeignKey(Country,on_delete=models.SET_NULL,related_name='products', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='products', null=True, blank=True)

    def __str__(self):
        return self.name

class Expense(models.Model):
    EXPENSE_TYPES = [
        ('products', 'Хариди маҳсулот'),
        ('taxi', 'Такси'),
        ('delivery', 'Доставка'),
        ('rent', 'Аренда'),
        ('other', 'Дигар'),
    ]
    expense_type = models.CharField(max_length=20, choices=EXPENSE_TYPES)
    name = models.CharField(max_length=200)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    date = models.DateField()
    description = models.TextField()
    product = models.ForeignKey(Product, on_delete=models.CASCADE, null=True, blank=True, related_name='expenses')
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name='expenses')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total(self):
        if self.quantity:
            return self.quantity * self.price
        return self.price
    
    def __str__(self):
        return f'{self.name} - {self.total}'

import myapp.signals
from django.db import models
from django.contrib.auth.models import User

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField()

    def __str__(self):
        return self.name
    
class Country(models.Model):
    country_name = models.CharField(max_length=100)
    shop = models.CharField(max_length=100)
    phone = models.CharField(max_length=20)
    address = models.CharField(max_length=255)
    description = models.TextField()

    def __str__(self):
        return f'{self.country_name} - {self.shop}'
    
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

    @property
    def total(self):
        if self.quantity:
            return self.quantity * self.price
        return self.price
    
    def __str__(self):
        return f'{self.name} - {self.total}'
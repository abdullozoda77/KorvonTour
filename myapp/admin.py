from django.contrib import admin
from .models import Category, Product, Country, Sklad, Expense

@admin.register(Sklad)
class SkladAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'address', 'map_x', 'map_y', 'lat', 'lng')
    list_filter = ('user',)
    search_fields = ('name', 'address')

admin.site.register(Category)
admin.site.register(Product)
admin.site.register(Country)
admin.site.register(Expense)

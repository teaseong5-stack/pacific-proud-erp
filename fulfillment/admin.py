from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from django.utils.html import format_html # ★ 이 줄이 필요합니다!

# 모든 모델 가져오기
from .models import (
    Partner, Zone, Location, Product, Purchase, PurchaseItem, 
    Inventory, Order, OrderItem, PickingList, Expense,
    Employee, Payroll, Payment
)
from .services import create_picking_list

# --- 인라인 설정 ---
class PickingListInline(admin.TabularInline):
    model = PickingList
    extra = 0
    readonly_fields = ('inventory', 'allocated_qty')
    can_delete = False
    verbose_name = "피킹 지시 내역"

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1

class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1

# --- Admin 등록 ---

@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'partner_type', 'owner_name', 'phone', 'display_balance')
    list_filter = ('partner_type',)
    search_fields = ('name',)

    def display_balance(self, obj):
        balance = float(obj.current_balance)
        color = 'blue' if balance >= 0 else 'red'
        formatted_balance = "{:,.0f}".format(balance)
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} đ</span>',
            color, formatted_balance
        )
    display_balance.short_description = "현재 잔액 (미수/미지급)"

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('date', 'partner', 'payment_type', 'amount', 'method', 'memo')
    list_filter = ('payment_type', 'date', 'method')
    search_fields = ('partner__name', 'memo')
    date_hierarchy = 'date'

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'sku', 'price', 'purchase_price', 'storage_type')
    list_filter = ('category', 'storage_type')
    search_fields = ('name', 'sku')
    list_editable = ('price', 'purchase_price')

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'supplier', 'purchase_date', 'total_amount', 'status', 'is_bill_published')
    list_filter = ('status', 'purchase_date')
    inlines = [PurchaseItemInline]
    actions = ['action_receive_goods']

    def action_receive_goods(self, request, queryset):
        received_count = 0
        with transaction.atomic():
            for purchase in queryset:
                if purchase.status == 'RECEIVED': continue
                items = purchase.items.all()
                if not items: continue
                for item in items:
                    Inventory.objects.create(
                        product=item.product, location=item.target_location,
                        quantity=item.quantity, batch_number=f"PUR-{purchase.id}-{timezone.now().strftime('%y%m%d')}",
                        received_date=timezone.now().date(), expiry_date=item.expiry_date
                    )
                    item.product.purchase_price = item.unit_cost
                    item.product.save()
                purchase.status = 'RECEIVED'
                purchase.save()
                received_count += 1
        if received_count > 0:
            self.message_user(request, f"{received_count}건 입고 처리 완료.")
    action_receive_goods.short_description = "📦 입고 처리 및 재고 자동생성"

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'client', 'status', 'order_date', 'total_revenue', 'gross_profit')
    list_filter = ('status', 'order_date')
    inlines = [OrderItemInline, PickingListInline]
    actions = ['action_allocate_stock']

    def action_allocate_stock(self, request, queryset):
        success_count = 0
        for order in queryset:
            try:
                create_picking_list(order)
                success_count += 1
            except Exception as e:
                self.message_user(request, f"주문 #{order.id} 오류: {e}", level=messages.ERROR)
        if success_count > 0:
            self.message_user(request, f"{success_count}건 재고 할당 완료.")
    action_allocate_stock.short_description = "재고 할당 및 피킹지시(FEFO)"

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('date', 'category', 'description', 'amount', 'has_proof')
    list_filter = ('category', 'date')
    date_hierarchy = 'date'
    
    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context)
        try:
            qs = response.context_data['cl'].queryset
            total = sum(item.amount for item in qs)
            response.context_data['title'] = f"지출 내역 (총 합계: {total:,.0f} đ)"
        except (AttributeError, KeyError):
            pass
        return response

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'position', 'department', 'base_salary', 'join_date', 'is_active')
    search_fields = ('name',)
    list_filter = ('department', 'is_active')

@admin.register(Payroll)
class PayrollAdmin(admin.ModelAdmin):
    list_display = ('month_label', 'payment_date', 'employee', 'total_amount', 'link_to_expense')
    list_filter = ('month_label', 'payment_date')
    
    def get_changeform_initial_data(self, request):
        return {'month_label': timezone.now().strftime('%Y-%m')}

    def link_to_expense(self, obj):
        return "✅ 비용처리 완료" if obj.related_expense else "❌ 미처리"
    link_to_expense.short_description = "회계 연동"

# 나머지 모델 등록
admin.site.register(Zone)
admin.site.register(Location)
admin.site.register(Inventory)
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncDay
from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from .utils import export_to_excel # 방금 만든 함수 import

# 모델 전체 임포트
from .models import (
    Partner, Product, Purchase, Inventory, Order, OrderItem, 
    PickingList, Expense, Employee, Payroll, Payment, Zone, Location,
    CompanyInfo
)
# ★ 폼 전체 임포트 (이 부분이 빠져서 에러가 났을 겁니다)
from .forms import (
    InboundForm, ProductForm, PartnerForm, 
    InventoryForm, PurchaseForm, OrderForm,
    ExpenseForm, EmployeeForm, PayrollForm, CompanyInfoForm,
    PurchaseCreateFormSet, OrderCreateFormSet # 폼셋도 포함
)
from .utils import generate_barcode_image

# --- 1. 대시보드 ---
def dashboard(request):
    today = timezone.now().date()
    this_month_start = today.replace(day=1)

    today_revenue = OrderItem.objects.filter(
        order__order_date__date=today, order__status='SHIPPED'
    ).aggregate(s=Sum('final_amount'))['s'] or 0

    month_orders = Order.objects.filter(order_date__date__gte=this_month_start, status='SHIPPED')
    month_revenue = month_orders.aggregate(s=Sum('total_revenue'))['s'] or 0
    month_cogs = month_orders.aggregate(s=Sum('total_cogs'))['s'] or 0
    month_expenses = Expense.objects.filter(date__gte=this_month_start).aggregate(s=Sum('amount'))['s'] or 0
    month_profit = (month_revenue - month_cogs) - month_expenses

    partners = Partner.objects.all()
    total_receivable = 0
    total_payable = 0
    for p in partners:
        balance = p.current_balance
        if balance > 0: total_receivable += balance
        elif balance < 0: total_payable += abs(balance)

    last_7_days = today - timedelta(days=6)
    daily_sales_qs = Order.objects.filter(
        order_date__date__gte=last_7_days, status='SHIPPED'
    ).annotate(day=TruncDay('order_date')).values('day').annotate(total=Sum('total_revenue')).order_by('day')
    
    chart_dates = [d['day'].strftime('%m-%d') for d in daily_sales_qs]
    chart_revenues = [int(d['total']) for d in daily_sales_qs]

    expense_qs = Expense.objects.filter(date__gte=this_month_start).values('category').annotate(total=Sum('amount'))
    expense_labels = [ex['category'] for ex in expense_qs]
    expense_data = [int(ex['total']) for ex in expense_qs]

    expiring = Inventory.objects.filter(expiry_date__lte=today+timedelta(days=7), quantity__gt=0).order_by('expiry_date')[:5]
    recent_orders = Order.objects.order_by('-order_date')[:5]

    context = {
        'today_revenue': today_revenue, 'month_profit': month_profit,
        'total_receivable': total_receivable, 'total_payable': total_payable,
        'chart_dates': chart_dates, 'chart_revenues': chart_revenues,
        'expense_labels': expense_labels, 'expense_data': expense_data,
        'expiring': expiring, 'recent_orders': recent_orders,
    }
    return render(request, 'fulfillment/dashboard.html', context)

# --- 2. 물류 프로세스 (입고/라벨/출고/명세서) ---
def inbound_create(request):
    if request.method == 'POST':
        form = InboundForm(request.POST)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.batch_number = f"{timezone.now().strftime('%Y%m%d')}-{inv.product.sku}"
            inv.save()
            return redirect('fulfillment:print_label', inventory_id=inv.id)
    else: form = InboundForm()
    return render(request, 'fulfillment/inbound_form.html', {'form': form})

def print_label(request, inventory_id):
    inv = get_object_or_404(Inventory, id=inventory_id)
    return render(request, 'fulfillment/print_label.html', {'inventory': inv, 'barcode_img': generate_barcode_image(inv.batch_number)})

def process_weight(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        for picking in order.picking_lists.all():
            w = request.POST.get(f'weight_{picking.id}')
            if w: picking.picked_weight = float(w); picking.picked = True; picking.save()
        
        for item in order.items.all():
            related_pickings = order.picking_lists.filter(inventory__product=item.product)
            total_w = sum(p.picked_weight or 0 for p in related_pickings)
            if total_w > 0: item.supplied_weight = total_w; item.save()
            
        order.status = 'SHIPPED'
        order.total_revenue = sum(item.final_amount or 0 for item in order.items.all())
        order.total_cogs = order.total_revenue * Decimal('0.7')
        order.save()
        return redirect('fulfillment:generate_invoice', order_id=order.id)
    return render(request, 'fulfillment/process_weight.html', {'order': order})

def generate_invoice_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    items = order.items.all()
    my_company = CompanyInfo.objects.first()
    if not my_company: my_company = CompanyInfo(name="(회사정보 미설정)")
    
    # 미수금 계산
    current_total = order.total_revenue
    total_balance = 0
    previous_balance = 0
    if order.client:
        total_balance = order.client.current_balance
        previous_balance = total_balance - current_total

    context = {
        'order': order, 'items': items, 'company': my_company, 'today': timezone.now().date(),
        'previous_balance': previous_balance, 'total_balance': total_balance,
    }
    return render(request, 'fulfillment/invoice_pdf.html', context)

# --- 3. 회사 정보 설정 ---
def company_update(request):
    company = CompanyInfo.objects.first()
    if not company: company = CompanyInfo.objects.create(name="우리회사(기본)")

    if request.method == 'POST':
        form = CompanyInfoForm(request.POST, instance=company)
        if form.is_valid(): form.save(); return redirect('fulfillment:dashboard')
    else: form = CompanyInfoForm(instance=company)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '🏢 우리 회사 정보 설정'})

# --- 4. 리포트 ---
def monthly_report(request):
    today = timezone.now().date()
    start_of_month = today.replace(day=1)
    orders = Order.objects.filter(order_date__date__gte=start_of_month, order_date__date__lte=today, status='SHIPPED')
    total_revenue = orders.aggregate(s=Sum('total_revenue'))['s'] or 0
    total_cogs = orders.aggregate(s=Sum('total_cogs'))['s'] or 0
    gross_profit = total_revenue - total_cogs
    expenses = Expense.objects.filter(date__gte=start_of_month, date__lte=today)
    total_expense = expenses.aggregate(s=Sum('amount'))['s'] or 0
    operating_profit = gross_profit - total_expense
    op_margin = round((operating_profit / total_revenue * 100), 1) if total_revenue > 0 else 0
    context = {
        'year': today.year, 'month': today.month, 'total_revenue': total_revenue, 'total_cogs': total_cogs,
        'gross_profit': gross_profit, 'total_expense': total_expense, 'operating_profit': operating_profit,
        'op_margin': op_margin, 'expense_list': expenses.values('category').annotate(sum=Sum('amount')).order_by('-sum'),
    }
    return render(request, 'fulfillment/monthly_report.html', context)

# --- 5. 조회 및 관리 (리스트/수정/삭제) ---

def inventory_list(request):
    inventories = Inventory.objects.filter(quantity__gt=0).select_related('product', 'location__zone').order_by('product__name')
    return render(request, 'fulfillment/inventory_list.html', {'inventories': inventories})

def inventory_update(request, pk):
    obj = get_object_or_404(Inventory, pk=pk)
    if request.method == 'POST':
        form = InventoryForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:inventory_list')
    else: form = InventoryForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '재고 수정'})

def inventory_delete(request, pk):
    obj = get_object_or_404(Inventory, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:inventory_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:inventory_list'})

# --- 발주/매입 (팝업 등록 & 폼셋 수정) ---
def purchase_list(request):
    purchases = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    form = PurchaseForm(initial={'purchase_date': timezone.now().date()})
    products_all = Product.objects.all()
    locations_all = Location.objects.filter(is_active=True)
    return render(request, 'fulfillment/purchase_list.html', {
        'purchases': purchases, 'form': form, 'products_all': products_all, 'locations_all': locations_all
    })

def purchase_create(request):
    """신규 발주 등록 (헤더+품목)"""
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseCreateFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            purchase = form.save()
            items = formset.save(commit=False)
            for item in items:
                item.purchase = purchase
                item.unit_cost = item.product.purchase_price
                item.save()
            purchase.total_amount = sum(i.quantity * i.unit_cost for i in purchase.items.all())
            purchase.save()
            return redirect('fulfillment:purchase_list')
    return redirect('fulfillment:purchase_list')

def purchase_update(request, pk):
    """발주 수정 (폼셋 사용)"""
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        form = PurchaseForm(request.POST, instance=purchase)
        formset = PurchaseCreateFormSet(request.POST, instance=purchase)
        if form.is_valid() and formset.is_valid():
            purchase = form.save()
            items = formset.save(commit=False)
            for obj in formset.deleted_objects: obj.delete()
            for item in items:
                item.purchase = purchase
                item.unit_cost = item.product.purchase_price
                item.save()
            purchase.total_amount = sum(i.quantity * i.unit_cost for i in purchase.items.all())
            purchase.save()
            return redirect('fulfillment:purchase_list')
    else:
        form = PurchaseForm(instance=purchase)
        formset = PurchaseCreateFormSet(instance=purchase)
    
    context = {
        'form': form, 'formset': formset, 'purchase': purchase,
        'products_all': Product.objects.all(),
        'locations_all': Location.objects.filter(is_active=True),
        'title': f'발주서 수정 (#{purchase.id})'
    }
    return render(request, 'fulfillment/purchase_edit.html', context)

def purchase_delete(request, pk):
    obj = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:purchase_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:purchase_list'})

# --- 주문/출고 (팝업 등록 & 폼셋 수정) ---
def order_list(request):
    orders = Order.objects.select_related('client').order_by('-order_date')
    form = OrderForm()
    products_all = Product.objects.all()
    return render(request, 'fulfillment/order_list.html', {
        'orders': orders, 'form': form, 'products_all': products_all
    })

def order_create(request):
    """신규 주문 등록 (헤더+품목)"""
    if request.method == 'POST':
        form = OrderForm(request.POST)
        formset = OrderCreateFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            order = form.save()
            items = formset.save(commit=False)
            total_rev = 0
            for item in items:
                item.order = order
                item.final_amount = item.quantity * item.product.price
                total_rev += item.final_amount
                item.save()
            order.total_revenue = total_rev
            order.save()
            return redirect('fulfillment:order_list')
    return redirect('fulfillment:order_list')

def order_update(request, pk):
    """주문 수정 (폼셋 사용)"""
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order)
        formset = OrderCreateFormSet(request.POST, instance=order)
        if form.is_valid() and formset.is_valid():
            order = form.save()
            items = formset.save(commit=False)
            for obj in formset.deleted_objects: obj.delete()
            total_rev = 0
            for item in items:
                item.order = order
                item.final_amount = item.quantity * item.product.price
                item.save()
            order.total_revenue = sum(i.final_amount for i in order.items.all())
            order.save()
            return redirect('fulfillment:order_list')
    else:
        form = OrderForm(instance=order)
        formset = OrderCreateFormSet(instance=order)

    context = {
        'form': form, 'formset': formset, 'order': order,
        'products_all': Product.objects.all(),
        'title': f'주문서 수정 (#{order.id})'
    }
    return render(request, 'fulfillment/order_edit.html', context)

def order_delete(request, pk):
    obj = get_object_or_404(Order, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:order_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:order_list'})

# --- 나머지 ---
def expense_list(request):
    expenses = Expense.objects.order_by('-date')
    form = ExpenseForm()
    return render(request, 'fulfillment/expense_list.html', {'expenses': expenses, 'form': form})
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:expense_list')
def expense_update(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:expense_list')
    else: form = ExpenseForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '비용 수정'})
def expense_delete(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:expense_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:expense_list'})

def employee_list(request):
    employees = Employee.objects.order_by('department', 'name')
    form = EmployeeForm()
    return render(request, 'fulfillment/employee_list.html', {'employees': employees, 'form': form})
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:employee_list')
def employee_update(request, pk):
    obj = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:employee_list')
    else: form = EmployeeForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '직원 정보 수정'})
def employee_delete(request, pk):
    obj = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:employee_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:employee_list'})

def payroll_list(request):
    payrolls = Payroll.objects.select_related('employee').order_by('-payment_date')
    form = PayrollForm(initial={'month_label': timezone.now().strftime('%Y-%m')})
    return render(request, 'fulfillment/payroll_list.html', {'payrolls': payrolls, 'form': form})
def payroll_create(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:payroll_list')
def payroll_update(request, pk):
    obj = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        form = PayrollForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:payroll_list')
    else: form = PayrollForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '급여 내역 수정'})
def payroll_delete(request, pk):
    obj = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:payroll_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:payroll_list'})

def partner_list(request):
    partners = Partner.objects.order_by('name')
    form = PartnerForm()
    return render(request, 'fulfillment/partner_list.html', {'partners': partners, 'form': form})
def partner_create(request):
    if request.method == 'POST':
        form = PartnerForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:partner_list')
def partner_update(request, pk):
    obj = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST':
        form = PartnerForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:partner_list')
    else: form = PartnerForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '거래처 수정'})
def partner_delete(request, pk):
    obj = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:partner_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:partner_list'})

def product_list(request):
    products = Product.objects.order_by('category', 'name')
    form = ProductForm()
    return render(request, 'fulfillment/product_list.html', {'products': products, 'form': form})
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:product_list')
def product_update(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:product_list')
    else: form = ProductForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '상품 수정'})
def product_delete(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:product_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:product_list'})
    
def export_inventory_excel(request):
    """재고 현황 엑셀"""
    queryset = Inventory.objects.select_related('product', 'location__zone').order_by('product__name')
    columns = [
        ('상품명', 'product__name'),
        ('SKU', 'product__sku'),
        ('위치', 'location__code'),
        ('수량', 'quantity'),
        ('단위', 'product__unit'),
        ('유통기한', 'expiry_date'),
        ('배치번호', 'batch_number'),
    ]
    return export_to_excel(queryset, 'Inventory_List', columns)

def export_purchase_excel(request):
    """매입 내역 엑셀"""
    queryset = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    columns = [
        ('매입번호', 'id'),
        ('공급사', 'supplier__name'),
        ('매입일자', 'purchase_date'),
        ('총금액', 'total_amount'),
        ('상태', 'get_status_display'), # 메서드 호출 가능
        ('증빙유무', 'is_bill_published'),
    ]
    return export_to_excel(queryset, 'Purchase_List', columns)

def export_order_excel(request):
    """주문 내역 엑셀"""
    queryset = Order.objects.select_related('client').order_by('-order_date')
    columns = [
        ('주문번호', 'id'),
        ('납품처', 'client__name'),
        ('주문일시', 'order_date'),
        ('매출액', 'total_revenue'),
        ('원가', 'total_cogs'),
        ('이익(GP)', 'gross_profit'),
        ('상태', 'get_status_display'),
        ('메모', 'memo'),
    ]
    return export_to_excel(queryset, 'Order_List', columns)    
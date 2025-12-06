from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum
from django.db.models.functions import TruncDay
from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from django.contrib.auth.decorators import login_required

# 모델 전체 임포트
from .models import (
    Partner, Product, Purchase, Inventory, Order, OrderItem, 
    PickingList, Expense, Employee, Payroll, Payment, Zone, Location,
    CompanyInfo, BankAccount, BankTransaction, WorkLog
)
# 폼 전체 임포트 (SignUpForm 추가됨)
from .forms import (
    InboundForm, ProductForm, PartnerForm, 
    InventoryForm, PurchaseForm, OrderForm,
    ExpenseForm, EmployeeForm, PayrollForm, CompanyInfoForm,
    BankAccountForm, WorkLogForm, SignUpForm,
    PurchaseCreateFormSet, OrderCreateFormSet, BankTransactionForm, ZoneForm, LocationForm
)
from .utils import generate_barcode_image, export_to_excel

# --- 0. 인증 (회원가입/탈퇴) ★ 추가된 부분 ---
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user) # 가입 즉시 로그인
            return redirect('fulfillment:dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

def delete_account(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        return redirect('login')
    return render(request, 'registration/delete_account.html')

# --- 1. 대시보드 ---
@login_required
def dashboard(request):
    """CEO 대시보드 (누적 매출 추가)"""
    today = timezone.now().date()
    this_month_start = today.replace(day=1)

    # 1. [기존] 오늘 확정 매출
    today_revenue = OrderItem.objects.filter(
        order__order_date__date=today, order__status='SHIPPED'
    ).aggregate(s=Sum('final_amount'))['s'] or 0

    # 2. [신규/강조] 이번 달 누적 매출 (주문 기준)
    # SHIPPED(출고완료) 된 건만 집계합니다.
    month_orders = Order.objects.filter(order_date__date__gte=this_month_start, status='SHIPPED')
    month_revenue = month_orders.aggregate(s=Sum('total_revenue'))['s'] or 0
    
    # 3. 이번 달 영업이익 계산
    month_cogs = month_orders.aggregate(s=Sum('total_cogs'))['s'] or 0
    month_expenses = Expense.objects.filter(date__gte=this_month_start).aggregate(s=Sum('amount'))['s'] or 0
    month_profit = (month_revenue - month_cogs) - month_expenses

    # 4. 자금 현황
    partners = Partner.objects.all()
    total_receivable = 0
    total_payable = 0
    for p in partners:
        balance = p.current_balance
        if balance > 0: total_receivable += balance
        elif balance < 0: total_payable += abs(balance)

    # 5. 차트 데이터
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
        'today_revenue': today_revenue, 
        'month_revenue': month_revenue, # ★ 추가됨: 이번 달 누적 매출
        'month_profit': month_profit,
        'total_receivable': total_receivable, 
        'total_payable': total_payable,
        'chart_dates': chart_dates, 'chart_revenues': chart_revenues,
        'expense_labels': expense_labels, 'expense_data': expense_data,
        'expiring': expiring, 'recent_orders': recent_orders,
    }
    return render(request, 'fulfillment/dashboard.html', context)

# --- 2. 물류 프로세스 ---
@login_required
def inbound_create(request):
    if request.method == 'POST':
        form = InboundForm(request.POST)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.batch_number = f"{timezone.now().strftime('%Y%m%d')}-{inv.product.sku}"
            inv.save()
            return redirect('fulfillment:print_label', inventory_id=inv.id)
    else:
        form = InboundForm(initial={'expiry_date': timezone.now().date() + timedelta(days=365)})
    
    products = Product.objects.all()
    return render(request, 'fulfillment/inbound_form.html', {'form': form, 'products': products})

@login_required
def print_label(request, inventory_id):
    inv = get_object_or_404(Inventory, id=inventory_id)
    return render(request, 'fulfillment/print_label.html', {'inventory': inv, 'barcode_img': generate_barcode_image(inv.batch_number)})

@login_required
def process_weight(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        # 1. 피킹 리스트에 실측 무게만 업데이트 (재고 차감 X)
        for picking in order.picking_lists.all():
            w = request.POST.get(f'weight_{picking.id}')
            if w: 
                picking.picked_weight = float(w)
                picking.picked = True
                picking.save()
            
            # ★ 주의: 여기서는 inventory.quantity를 건드리지 않습니다!
            # (이미 create_picking_list에서 차감되었기 때문)
        
        # 2. 주문 아이템 금액 확정 (실측 중량 기준)
        for item in order.items.all():
            related_pickings = order.picking_lists.filter(inventory__product=item.product)
            total_w = sum(p.picked_weight or 0 for p in related_pickings)
            
            if total_w > 0: 
                item.supplied_weight = total_w
                item.save()
            
        # 3. 주문 상태 변경 (ALLOCATED -> SHIPPED)
        order.status = 'SHIPPED'
        order.total_revenue = sum(item.final_amount or 0 for item in order.items.all())
        order.total_cogs = order.total_revenue * Decimal('0.7') 
        order.save()
        
        return redirect('fulfillment:generate_invoice', order_id=order.id)
        
    return render(request, 'fulfillment/process_weight.html', {'order': order})

@login_required
def generate_invoice_pdf(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    items = order.items.all()
    my_company = CompanyInfo.objects.first()
    if not my_company: my_company = CompanyInfo(name="(회사정보 미설정)")
    
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
@login_required
def company_update(request):
    company = CompanyInfo.objects.first()
    if not company: company = CompanyInfo.objects.create(name="우리회사(기본)")

    if request.method == 'POST':
        form = CompanyInfoForm(request.POST, instance=company)
        if form.is_valid(): form.save(); return redirect('fulfillment:dashboard')
    else: form = CompanyInfoForm(instance=company)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '🏢 우리 회사 정보 설정'})

# --- 4. 리포트 ---
@login_required
def monthly_report(request):
    query_month = request.GET.get('month')
    if query_month:
        year, month = map(int, query_month.split('-'))
        start_date = timezone.datetime(year, month, 1).date()
    else:
        start_date = timezone.now().date().replace(day=1)

    if start_date.month == 12: next_month_start = start_date.replace(year=start_date.year + 1, month=1, day=1)
    else: next_month_start = start_date.replace(month=start_date.month + 1, day=1)

    orders = Order.objects.filter(order_date__gte=start_date, order_date__lt=next_month_start, status='SHIPPED')
    total_revenue = orders.aggregate(s=Sum('total_revenue'))['s'] or 0
    total_cogs = orders.aggregate(s=Sum('total_cogs'))['s'] or 0
    gross_profit = total_revenue - total_cogs

    expenses = Expense.objects.filter(date__gte=start_date, date__lt=next_month_start)
    total_expense = expenses.aggregate(s=Sum('amount'))['s'] or 0
    operating_profit = gross_profit - total_expense
    op_margin = round((operating_profit / total_revenue * 100), 1) if total_revenue > 0 else 0

    context = {
        'target_date': start_date, 'query_month': start_date.strftime('%Y-%m'),
        'total_revenue': total_revenue, 'total_cogs': total_cogs,
        'gross_profit': gross_profit, 'total_expense': total_expense, 'operating_profit': operating_profit,
        'op_margin': op_margin, 'expense_list': expenses.values('category').annotate(sum=Sum('amount')).order_by('-sum'),
    }
    return render(request, 'fulfillment/monthly_report.html', context)

# --- 5. 조회 및 관리 리스트 (검색/엑셀 포함) ---
@login_required
def inventory_list(request):
    inventories = Inventory.objects.filter(quantity__gt=0).select_related('product', 'location__zone').order_by('product__name')
    p_name = request.GET.get('p_name')
    sku = request.GET.get('sku')
    loc_id = request.GET.get('location')
    s_date = request.GET.get('start_date')
    e_date = request.GET.get('end_date')
    if p_name: inventories = inventories.filter(product__name__icontains=p_name)
    if sku: inventories = inventories.filter(product__sku__icontains=sku)
    if loc_id: inventories = inventories.filter(location_id=loc_id)
    if s_date: inventories = inventories.filter(expiry_date__gte=s_date)
    if e_date: inventories = inventories.filter(expiry_date__lte=e_date)
    locations = Location.objects.filter(is_active=True).select_related('zone').order_by('zone__name', 'code')
    return render(request, 'fulfillment/inventory_list.html', {'inventories': inventories, 'locations': locations})
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

@login_required
def purchase_list(request):
    purchases = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    supplier_id = request.GET.get('supplier')
    status = request.GET.get('status')
    if start_date: purchases = purchases.filter(purchase_date__gte=start_date)
    if end_date: purchases = purchases.filter(purchase_date__lte=end_date)
    if supplier_id: purchases = purchases.filter(supplier_id=supplier_id)
    if status: purchases = purchases.filter(status=status)
    suppliers = Partner.objects.filter(partner_type__in=['SUPPLIER', 'BOTH'])
    locations_all = Location.objects.filter(is_active=True)
    products_all = Product.objects.all()
    form = PurchaseForm(initial={'purchase_date': timezone.now().date()})
    return render(request, 'fulfillment/purchase_list.html', {
        'purchases': purchases, 'form': form, 'products_all': products_all, 'locations_all': locations_all, 'suppliers': suppliers
    })
def purchase_create(request):
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
    context = {'form': form, 'formset': formset, 'purchase': purchase, 'products_all': Product.objects.all(), 'locations_all': Location.objects.filter(is_active=True), 'title': f'발주서 수정 (#{purchase.id})'}
    return render(request, 'fulfillment/purchase_edit.html', context)
def purchase_delete(request, pk):
    obj = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:purchase_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:purchase_list'})

@login_required
def order_list(request):
    orders = Order.objects.select_related('client').order_by('-order_date')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    client_id = request.GET.get('client')
    status = request.GET.get('status')
    if start_date: orders = orders.filter(order_date__date__gte=start_date)
    if end_date: orders = orders.filter(order_date__date__lte=end_date)
    if client_id: orders = orders.filter(client_id=client_id)
    if status: orders = orders.filter(status=status)
    clients = Partner.objects.filter(partner_type__in=['CLIENT', 'BOTH'])
    products_all = Product.objects.all()
    form = OrderForm()
    return render(request, 'fulfillment/order_list.html', {
        'orders': orders, 'form': form, 'products_all': products_all, 'clients': clients
    })
def order_create(request):
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
    context = {'form': form, 'formset': formset, 'order': order, 'products_all': Product.objects.all(), 'title': f'주문서 수정 (#{order.id})'}
    return render(request, 'fulfillment/order_edit.html', context)
def order_delete(request, pk):
    obj = get_object_or_404(Order, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:order_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:order_list'})

@login_required
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

@login_required
def employee_list(request):
    employees = Employee.objects.order_by('department', 'name')
    name_query = request.GET.get('name')
    dept_query = request.GET.get('department')
    status_query = request.GET.get('status')
    if name_query: employees = employees.filter(name__icontains=name_query)
    if dept_query: employees = employees.filter(department__icontains=dept_query)
    if status_query:
        is_active = True if status_query == 'active' else False
        employees = employees.filter(is_active=is_active)
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

@login_required
def payroll_list(request):
    payrolls = Payroll.objects.select_related('employee').order_by('-payment_date')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    emp_name = request.GET.get('emp_name')
    if start_date: payrolls = payrolls.filter(payment_date__gte=start_date)
    if end_date: payrolls = payrolls.filter(payment_date__lte=end_date)
    if emp_name: payrolls = payrolls.filter(employee__name__icontains=emp_name)
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

@login_required
def partner_list(request):
    partners = Partner.objects.order_by('name')
    name_query = request.GET.get('name')
    type_query = request.GET.get('partner_type')
    if name_query: partners = partners.filter(name__icontains=name_query)
    if type_query: partners = partners.filter(partner_type=type_query)
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

@login_required
def product_list(request):
    products = Product.objects.order_by('category', 'name')
    name_query = request.GET.get('name')
    category_query = request.GET.get('category')
    storage_query = request.GET.get('storage')
    if name_query: products = products.filter(name__icontains=name_query)
    if category_query: products = products.filter(category=category_query)
    if storage_query: products = products.filter(storage_type=storage_query)
    form = ProductForm()
    from .models import ProductCategory, StorageType
    return render(request, 'fulfillment/product_list.html', {'products': products, 'form': form, 'categories': ProductCategory.choices, 'storages': StorageType.choices})
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

# --- 6. 자금/업무일지 ---
@login_required
def bank_list(request):
    """법인 통장 목록 및 잔액 조회 (거래 등록 폼 추가)"""
    accounts = BankAccount.objects.filter(is_active=True)
    
    # 1. 계좌 생성 폼
    form = BankAccountForm()
    
    # 2. 거래 등록 폼 (팝업용)
    transaction_form = BankTransactionForm(initial={'date': timezone.now().date()})
    
    return render(request, 'fulfillment/bank_list.html', {
        'accounts': accounts, 
        'form': form,
        'transaction_form': transaction_form # ★ 템플릿으로 전달
    })

@login_required
def bank_transaction_create(request):
    """입출금 거래 저장"""
    if request.method == 'POST':
        form = BankTransactionForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('fulfillment:bank_list')
    return redirect('fulfillment:bank_list')
def bank_create(request):
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:bank_list')
def bank_detail(request, pk):
    account = get_object_or_404(BankAccount, pk=pk)
    transactions = account.transactions.order_by('-date', '-id')
    return render(request, 'fulfillment/bank_detail.html', {'account': account, 'transactions': transactions})

@login_required
def worklog_list(request):
    logs = WorkLog.objects.select_related('employee').order_by('-date')
    q_date = request.GET.get('date')
    if q_date: logs = logs.filter(date=q_date)
    form = WorkLogForm(initial={'date': timezone.now().date()})
    return render(request, 'fulfillment/worklog_list.html', {'logs': logs, 'form': form})
def worklog_create(request):
    if request.method == 'POST':
        form = WorkLogForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:worklog_list')
def worklog_update(request, pk):
    obj = get_object_or_404(WorkLog, pk=pk)
    if request.method == 'POST':
        form = WorkLogForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:worklog_list')
    else: form = WorkLogForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '업무일지 수정'})
def worklog_delete(request, pk):
    obj = get_object_or_404(WorkLog, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:worklog_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:worklog_list'})

# --- 7. 엑셀 다운로드 ---
@login_required
def export_inventory_excel(request):
    queryset = Inventory.objects.filter(quantity__gt=0).select_related('product', 'location__zone').order_by('product__name')
    # ... 검색 로직 ...
    columns = [('상품명', 'product__name'), ('SKU', 'product__sku'), ('위치', 'location__code'), ('수량', 'quantity'), ('유통기한', 'expiry_date')]
    return export_to_excel(queryset, 'Inventory_List', columns)

def export_purchase_excel(request):
    queryset = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    # ... 검색 로직 ...
    columns = [('매입번호', 'id'), ('공급사', 'supplier__name'), ('매입일자', 'purchase_date'), ('총금액', 'total_amount'), ('상태', 'get_status_display')]
    return export_to_excel(queryset, 'Purchase_List', columns)

def export_order_excel(request):
    queryset = Order.objects.select_related('client').order_by('-order_date')
    # ... 검색 로직 ...
    columns = [('주문번호', 'id'), ('납품처', 'client__name'), ('주문일시', 'order_date'), ('매출액', 'total_revenue'), ('상태', 'get_status_display')]
    return export_to_excel(queryset, 'Order_List', columns)
    
"""창고 및 위치 관리"""
@login_required
def location_list(request):
    """창고 및 위치 관리 (구역별 재고 현황 팝업 기능 추가)"""
    # prefetch_related를 사용해 '위치'와 그 위치에 있는 '재고', '상품' 정보를 미리 가져옵니다. (성능 최적화)
    zones = Zone.objects.prefetch_related(
        'locations', 
        'locations__inventory_set', 
        'locations__inventory_set__product'
    ).order_by('name')
    
    zone_form = ZoneForm()
    location_form = LocationForm()
    
    return render(request, 'fulfillment/location_list.html', {
        'zones': zones,
        'zone_form': zone_form,
        'location_form': location_form
    })

"""창고 및 위치 관리"""
def zone_create(request):
    """구역 등록"""
    if request.method == 'POST':
        form = ZoneForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:location_list')

"""창고 및 위치 관리"""
def location_create(request):
    """위치 등록"""
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:location_list')

"""창고 및 위치 관리"""
def zone_delete(request, pk):
    """구역 삭제"""
    obj = get_object_or_404(Zone, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:location_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:location_list'})

"""창고 및 위치 관리"""
def location_delete(request, pk):
    """위치 삭제"""
    obj = get_object_or_404(Location, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:location_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:location_list'})

# fulfillment/views.py 맨 아래 추가

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
# PDF 생성 라이브러리 (설치되어 있어야 함, 없으면 생략하고 HTML 본문으로 보냄)
# 여기서는 간단히 'HTML 이메일'을 보내는 방식으로 구현합니다.

def email_invoice(request, order_id):
    """거래명세서 이메일 발송"""
    order = get_object_or_404(Order, id=order_id)
    
    if not order.client.email:
        # 고객 이메일이 없으면 에러 메시지 (실제로는 알림창 띄우기)
        return HttpResponse("고객(거래처) 정보에 이메일이 등록되지 않았습니다.")

    # 이메일 본문 생성 (HTML)
    html_content = render_to_string('fulfillment/invoice_email_content.html', {
        'order': order,
        'items': order.items.all()
    })

    # 이메일 객체 생성
    email = EmailMessage(
        subject=f"[PACIFIC PROUD] 거래명세서 (주문번호 #{order.id})",
        body=html_content,
        from_email='noreply@pacificproud.com', # 발신자 (설정 필요)
        to=[order.client.email], # 수신자 (Partner 모델에 email 필드 필요)
    )
    email.content_subtype = "html" # HTML 형식

    try:
        email.send()
        return HttpResponse("이메일이 성공적으로 발송되었습니다.")
    except Exception as e:
        return HttpResponse(f"발송 실패: {e}")    
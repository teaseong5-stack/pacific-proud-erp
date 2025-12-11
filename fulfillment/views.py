from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q
from django.db.models.functions import TruncDay
from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages

# 모델 전체 임포트
from .models import (
    Partner, Product, Purchase, PurchaseItem, Inventory, Order, OrderItem, 
    PickingList, Expense, Employee, Payroll, Payment, Zone, Location,
    CompanyInfo, BankAccount, BankTransaction, WorkLog
)
# ★ 폼 전체 임포트 (ZoneForm, LocationForm이 여기에 꼭 있어야 합니다!)
from .forms import (
    InboundForm, ProductForm, PartnerForm, 
    InventoryForm, PurchaseForm, OrderForm,
    ExpenseForm, EmployeeForm, PayrollForm, CompanyInfoForm,
    BankAccountForm, WorkLogForm, BankTransactionForm, SignUpForm,
    PurchaseCreateFormSet, OrderCreateFormSet, PaymentQuickForm,
    ZoneForm, LocationForm  # <--- 이 부분이 핵심입니다.
)
# 유틸리티
from .utils import generate_barcode_image, export_to_excel
from .services import create_picking_list

# ==========================================
# 0. 인증 (회원가입/탈퇴)
# ==========================================
def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('fulfillment:dashboard')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        user.delete()
        return redirect('login')
    return render(request, 'registration/delete_account.html')

# ==========================================
# 1. 경영 대시보드
# ==========================================
@login_required
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
        'today_revenue': today_revenue, 'month_revenue': month_revenue,
        'month_profit': month_profit, 'total_receivable': total_receivable, 'total_payable': total_payable,
        'chart_dates': chart_dates, 'chart_revenues': chart_revenues,
        'expense_labels': expense_labels, 'expense_data': expense_data,
        'expiring': expiring, 'recent_orders': recent_orders,
    }
    return render(request, 'fulfillment/dashboard.html', context)

# ==========================================
# 2. 물류 프로세스
# ==========================================
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
def order_allocate(request, pk):
    order = get_object_or_404(Order, pk=pk)
    try:
        create_picking_list(order)
        messages.success(request, f"주문 #{order.id} 피킹 지시 완료")
    except Exception as e:
        messages.error(request, f"오류: {e}")
    return redirect('fulfillment:order_list')

@login_required
def process_weight(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        if order.status == 'SHIPPED': return redirect('fulfillment:generate_invoice', order_id=order.id)
        
        for picking in order.picking_lists.all():
            w = request.POST.get(f'weight_{picking.id}')
            if w: 
                picking.picked_weight = float(w); picking.picked = True; picking.save()
            # 재고 차감 로직은 services.py(피킹지시)에서 수행됨. 중복차감 방지.
        
        total_rev = 0
        real_cogs = 0
        for item in order.items.all():
            related_picks = order.picking_lists.filter(inventory__product=item.product)
            total_w = sum(p.picked_weight or 0 for p in related_picks)
            if total_w > 0: item.supplied_weight = total_w; item.save()
            
            total_rev += item.final_amount or 0
            qty = item.supplied_weight if (item.supplied_weight and item.product.unit.lower() in ['kg','g']) else item.quantity
            real_cogs += (qty * item.product.purchase_price)

        order.status = 'SHIPPED'
        order.total_revenue = total_rev
        order.total_cogs = real_cogs
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
        initial = order.client.initial_balance
        past_sales = Order.objects.filter(client=order.client, status='SHIPPED').filter(Q(order_date__lt=order.order_date)|Q(order_date=order.order_date, id__lt=order.id)).aggregate(s=Sum('total_revenue'))['s'] or 0
        total_paid = Payment.objects.filter(partner=order.client, payment_type='INBOUND', date__lte=order.order_date.date()).aggregate(s=Sum('amount'))['s'] or 0
        previous_balance = (initial + past_sales) - total_paid
        total_balance = previous_balance + current_total

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

    purchases = Purchase.objects.filter(purchase_date__gte=start_date, purchase_date__lt=next_month_start, status='RECEIVED')
    total_purchase_amt = purchases.aggregate(s=Sum('total_amount'))['s'] or 0

    context = {
        'target_date': start_date, 'query_month': start_date.strftime('%Y-%m'),
        'total_revenue': total_revenue, 'total_cogs': total_cogs, 'gross_profit': gross_profit,
        'total_expense': total_expense, 'operating_profit': operating_profit, 'op_margin': op_margin,
        'total_purchase_amount': total_purchase_amt,
        'expense_list': expenses.values('category').annotate(sum=Sum('amount')).order_by('-sum'),
    }
    return render(request, 'fulfillment/monthly_report.html', context)

# --- 5. 조회 및 관리 리스트 ---

@login_required
def inventory_list(request):
    inventories = Inventory.objects.filter(quantity__gt=0).select_related('product', 'location__zone').order_by('product__name')
    p_name = request.GET.get('p_name'); sku = request.GET.get('sku'); loc_id = request.GET.get('location')
    s_date = request.GET.get('start_date'); e_date = request.GET.get('end_date')
    if p_name: inventories = inventories.filter(product__name__icontains=p_name)
    if sku: inventories = inventories.filter(product__sku__icontains=sku)
    if loc_id: inventories = inventories.filter(location_id=loc_id)
    if s_date: inventories = inventories.filter(expiry_date__gte=s_date)
    if e_date: inventories = inventories.filter(expiry_date__lte=e_date)
    locations = Location.objects.filter(is_active=True).select_related('zone').order_by('zone__name', 'code')
    return render(request, 'fulfillment/inventory_list.html', {'inventories': inventories, 'locations': locations})
@login_required
def inventory_update(request, pk):
    obj = get_object_or_404(Inventory, pk=pk)
    if request.method == 'POST':
        form = InventoryForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:inventory_list')
    else: form = InventoryForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '재고 수정'})
@login_required
def inventory_delete(request, pk):
    obj = get_object_or_404(Inventory, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:inventory_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:inventory_list'})

@login_required
def purchase_list(request):
    """발주 현황 리스트 + 신규 발주 등록 팝업 처리"""
    
    # 1. 기존 리스트 조회 로직 (그대로 유지)
    purchases = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    supplier_id = request.GET.get('supplier')
    status = request.GET.get('status')

    if start_date: purchases = purchases.filter(purchase_date__gte=start_date)
    if end_date: purchases = purchases.filter(purchase_date__lte=end_date)
    if supplier_id: purchases = purchases.filter(supplier_id=supplier_id)
    if status: purchases = purchases.filter(status=status)

   # 2. 팝업창 데이터
    suppliers = Partner.objects.filter(partner_type__in=['SUPPLIER', 'BOTH'])
    products_all = Product.objects.all()
    locations_all = Location.objects.filter(is_active=True)
    
    # 3. ★ 수정된 부분: prefix='items' 추가 (이름표 고정)
    form = PurchaseForm(initial={'purchase_date': timezone.now().date()})
    
    # prefix='items'를 넣으면 HTML ID가 'id_items-TOTAL_FORMS'로 고정됩니다.
    formset = PurchaseCreateFormSet(queryset=PurchaseItem.objects.none(), prefix='items') 

    context = {
        'purchases': purchases,
        'suppliers': suppliers,
        'products_all': products_all,
        'locations_all': locations_all,
        'form': form,
        'formset': formset
    }
    return render(request, 'fulfillment/purchase_list.html', context)

@login_required
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
            purchase.update_total_amount()
            return redirect('fulfillment:purchase_list')
    return redirect('fulfillment:purchase_list')
@login_required
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
            purchase.update_total_amount()
            return redirect('fulfillment:purchase_list')
    else:
        form = PurchaseForm(instance=purchase)
        formset = PurchaseCreateFormSet(instance=purchase)
    context = {'form': form, 'formset': formset, 'purchase': purchase, 'products_all': Product.objects.all(), 'locations_all': Location.objects.filter(is_active=True), 'title': f'발주서 수정 (#{purchase.id})'}
    return render(request, 'fulfillment/purchase_edit.html', context)
@login_required
def purchase_delete(request, pk):
    obj = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:purchase_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:purchase_list'})
@login_required
def order_list(request):
    """주문 현황 리스트 + 신규 주문 등록 팝업 처리"""
    
    # 1. 기존 리스트 조회 로직
    orders = Order.objects.select_related('client').order_by('-order_date')
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    client_id = request.GET.get('client')
    status = request.GET.get('status')

    if start_date: orders = orders.filter(order_date__date__gte=start_date)
    if end_date: orders = orders.filter(order_date__date__lte=end_date)
    if client_id: orders = orders.filter(client_id=client_id)
    if status: orders = orders.filter(status=status)

    # 2. 팝업창에 필요한 데이터 준비
    clients = Partner.objects.filter(partner_type__in=['CLIENT', 'BOTH'])
    products_all = Product.objects.all()
    
    # 3. ★ 신규 등록용 폼 & 폼셋 생성 (팝업용 빈 종이 준비)
    form = OrderForm(initial={'status': 'PENDING'}) # 기본 상태: 주문접수
    
    # prefix='items'를 넣어 자바스크립트가 찾기 쉽게 만듭니다.
    # queryset=...none()을 해야 빈 줄만 나옵니다.
    formset = OrderCreateFormSet(queryset=OrderItem.objects.none(), prefix='items')

    context = {
        'orders': orders,
        'clients': clients,
        'products_all': products_all,
        'form': form,
        'formset': formset # ★ 핵심 데이터
    }
    return render(request, 'fulfillment/order_list.html', context)
@login_required
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
                item.order = order; item.final_amount = item.quantity * item.product.price; item.save()
                total_rev += item.final_amount
            order.total_revenue = sum(i.final_amount for i in order.items.all())
            order.save()
            return redirect('fulfillment:order_list')
    else:
        form = OrderForm(instance=order)
        formset = OrderCreateFormSet(instance=order)
    context = {'form': form, 'formset': formset, 'order': order, 'products_all': Product.objects.all(), 'title': f'주문서 수정 (#{order.id})'}
    return render(request, 'fulfillment/order_edit.html', context)
@login_required
def order_delete(request, pk):
    obj = get_object_or_404(Order, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:order_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:order_list'})

@login_required
def expense_list(request):
    expenses = Expense.objects.order_by('-date')
    form = ExpenseForm()
    return render(request, 'fulfillment/expense_list.html', {'expenses': expenses, 'form': form})
@login_required
def expense_create(request):
    if request.method == 'POST':
        form = ExpenseForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:expense_list')
@login_required
def expense_update(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:expense_list')
    else: form = ExpenseForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '비용 수정'})
@login_required
def expense_delete(request, pk):
    obj = get_object_or_404(Expense, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:expense_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:expense_list'})

@login_required
def employee_list(request):
    employees = Employee.objects.order_by('department', 'name')
    name_q = request.GET.get('name'); dept_q = request.GET.get('department'); stat_q = request.GET.get('status')
    if name_q: employees = employees.filter(name__icontains=name_q)
    if dept_q: employees = employees.filter(department__icontains=dept_q)
    if stat_q: employees = employees.filter(is_active=(stat_q=='active'))
    form = EmployeeForm()
    return render(request, 'fulfillment/employee_list.html', {'employees': employees, 'form': form})
@login_required
def employee_create(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:employee_list')
@login_required
def employee_update(request, pk):
    obj = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:employee_list')
    else: form = EmployeeForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '직원 정보 수정'})
@login_required
def employee_delete(request, pk):
    obj = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:employee_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:employee_list'})

@login_required
def payroll_list(request):
    payrolls = Payroll.objects.select_related('employee').order_by('-payment_date')
    s_date = request.GET.get('start_date'); e_date = request.GET.get('end_date'); emp_name = request.GET.get('emp_name')
    if s_date: payrolls = payrolls.filter(payment_date__gte=s_date)
    if e_date: payrolls = payrolls.filter(payment_date__lte=e_date)
    if emp_name: payrolls = payrolls.filter(employee__name__icontains=emp_name)
    form = PayrollForm(initial={'month_label': timezone.now().strftime('%Y-%m')})
    return render(request, 'fulfillment/payroll_list.html', {'payrolls': payrolls, 'form': form})
@login_required
def payroll_create(request):
    if request.method == 'POST':
        form = PayrollForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:payroll_list')
@login_required
def payroll_update(request, pk):
    obj = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST':
        form = PayrollForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:payroll_list')
    else: form = PayrollForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '급여 내역 수정'})
@login_required
def payroll_delete(request, pk):
    obj = get_object_or_404(Payroll, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:payroll_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:payroll_list'})

@login_required
def partner_list(request):
    partners = Partner.objects.order_by('name')
    name_q = request.GET.get('name'); type_q = request.GET.get('partner_type')
    if name_q: partners = partners.filter(name__icontains=name_q)
    if type_q: partners = partners.filter(partner_type=type_q)
    form = PartnerForm()
    return render(request, 'fulfillment/partner_list.html', {'partners': partners, 'form': form})
@login_required
def partner_create(request):
    if request.method == 'POST':
        form = PartnerForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:partner_list')
@login_required
def partner_update(request, pk):
    obj = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST':
        form = PartnerForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:partner_list')
    else: form = PartnerForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '거래처 수정'})
@login_required
def partner_delete(request, pk):
    obj = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:partner_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:partner_list'})
@login_required
def partner_detail(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    transactions = []
    
    # 1. 매출 내역
    if partner.partner_type in ['CLIENT', 'BOTH']:
        orders = partner.order_set.filter(status='SHIPPED')
        for o in orders:
            o.data_type='order'; o.type_label="매출"; o.amount=o.total_revenue; o.date=o.order_date.date(); o.link_id=o.id
            transactions.append(o)
    
    # 2. 매입 내역
    if partner.partner_type in ['SUPPLIER', 'BOTH']:
        purchases = partner.purchase_set.filter(status='RECEIVED')
        for p in purchases:
            p.data_type='purchase'; p.type_label="매입"; p.amount=p.total_amount; p.date=p.purchase_date; p.link_id=p.id
            transactions.append(p)
    
    # 3. 결제(입출금) 내역
    for pay in partner.payment_set.all():
        pay.data_type='payment'; pay.type_label=pay.get_payment_type_display(); pay.link_id=pay.id
        pay.calc_amount = -pay.amount
        transactions.append(pay)

    # 4. 정렬 및 잔액 계산
    transactions.sort(key=lambda x: x.date)
    running = partner.initial_balance
    ledger = []
    for t in transactions:
        change = getattr(t, 'calc_amount', t.amount)
        running += change
        ledger.append({
            'obj': t, 'date': t.date, 'type': t.type_label, 'data_type': getattr(t, 'data_type', 'payment'),
            'desc': str(t), 'change': change, 'balance': running
        })
    
    # 5. 팝업 폼
    initial = {'date': timezone.now().date()}
    if partner.partner_type == 'CLIENT': initial['payment_type'] = 'INBOUND'
    elif partner.partner_type == 'SUPPLIER': initial['payment_type'] = 'OUTBOUND'
    form = PaymentQuickForm(initial=initial)
    
    return render(request, 'fulfillment/partner_detail.html', {'partner': partner, 'ledger_data': ledger, 'form': form})

@login_required
def partner_payment_create(request, pk):
    partner = get_object_or_404(Partner, pk=pk)
    if request.method == 'POST':
        form = PaymentQuickForm(request.POST)
        if form.is_valid():
            pay = form.save(commit=False)
            pay.partner = partner; pay.save()
    return redirect('fulfillment:partner_detail', pk=pk)

@login_required
def payment_update(request, pk):
    pay = get_object_or_404(Payment, pk=pk)
    if request.method == 'POST':
        form = PaymentQuickForm(request.POST, instance=pay)
        if form.is_valid(): form.save(); return redirect('fulfillment:partner_detail', pk=pay.partner.id)
    else: form = PaymentQuickForm(instance=pay)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '입출금 수정'})

@login_required
def payment_delete(request, pk):
    pay = get_object_or_404(Payment, pk=pk)
    pid = pay.partner.id
    if request.method == 'POST': pay.delete(); return redirect('fulfillment:partner_detail', pk=pid)
    return render(request, 'fulfillment/common_delete.html', {'object': pay, 'back_url': 'fulfillment:partner_list'})    

@login_required
def product_list(request):
    products = Product.objects.order_by('category', 'name')
    name_q = request.GET.get('name'); cat_q = request.GET.get('category'); sto_q = request.GET.get('storage')
    if name_q: products = products.filter(name__icontains=name_q)
    if cat_q: products = products.filter(category=cat_q)
    if sto_q: products = products.filter(storage_type=sto_q)
    form = ProductForm()
    from .models import ProductCategory, StorageType
    return render(request, 'fulfillment/product_list.html', {'products': products, 'form': form, 'categories': ProductCategory.choices, 'storages': StorageType.choices})
@login_required
def product_create(request):
    if request.method == 'POST':
        form = ProductForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:product_list')
@login_required
def product_update(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    if request.method == 'POST':
        form = ProductForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:product_list')
    else: form = ProductForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '상품 수정'})
@login_required
def product_delete(request, pk):
    obj = get_object_or_404(Product, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:product_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:product_list'})

@login_required
def bank_list(request):
    accounts = BankAccount.objects.filter(is_active=True)
    form = BankAccountForm()
    trx_form = BankTransactionForm(initial={'date': timezone.now().date()})
    return render(request, 'fulfillment/bank_list.html', {'accounts': accounts, 'form': form, 'transaction_form': trx_form})
@login_required
def bank_create(request):
    if request.method == 'POST':
        form = BankAccountForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:bank_list')
@login_required
def bank_transaction_create(request):
    if request.method == 'POST':
        form = BankTransactionForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:bank_list')
@login_required
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
@login_required
def worklog_create(request):
    if request.method == 'POST':
        form = WorkLogForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:worklog_list')
@login_required
def worklog_update(request, pk):
    obj = get_object_or_404(WorkLog, pk=pk)
    if request.method == 'POST':
        form = WorkLogForm(request.POST, instance=obj)
        if form.is_valid(): form.save(); return redirect('fulfillment:worklog_list')
    else: form = WorkLogForm(instance=obj)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '업무일지 수정'})
@login_required
def worklog_delete(request, pk):
    obj = get_object_or_404(WorkLog, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:worklog_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:worklog_list'})

@login_required
def location_list(request):
    zones = Zone.objects.prefetch_related('locations', 'locations__inventory_set', 'locations__inventory_set__product').order_by('name')
    return render(request, 'fulfillment/location_list.html', {'zones': zones, 'zone_form': ZoneForm(), 'location_form': LocationForm()})
@login_required
def zone_create(request):
    if request.method == 'POST':
        form = ZoneForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:location_list')
@login_required
def location_create(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid(): form.save()
    return redirect('fulfillment:location_list')
@login_required
def zone_delete(request, pk):
    obj = get_object_or_404(Zone, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:location_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:location_list'})
@login_required
def location_delete(request, pk):
    obj = get_object_or_404(Location, pk=pk)
    if request.method == 'POST': obj.delete(); return redirect('fulfillment:location_list')
    return render(request, 'fulfillment/common_delete.html', {'object': obj, 'back_url': 'fulfillment:location_list'})

# --- 엑셀 다운로드 ---
@login_required
def export_inventory_excel(request):
    queryset = Inventory.objects.filter(quantity__gt=0).select_related('product', 'location__zone').order_by('product__name')
    p_name = request.GET.get('p_name'); sku = request.GET.get('sku'); loc_id = request.GET.get('location')
    s_date = request.GET.get('start_date'); e_date = request.GET.get('end_date')
    if p_name: queryset = queryset.filter(product__name__icontains=p_name)
    if sku: queryset = queryset.filter(product__sku__icontains=sku)
    if loc_id: queryset = queryset.filter(location_id=loc_id)
    if s_date: queryset = queryset.filter(expiry_date__gte=s_date)
    if e_date: queryset = queryset.filter(expiry_date__lte=e_date)
    columns = [('상품명', 'product__name'), ('SKU', 'product__sku'), ('위치', 'location__code'), ('수량', 'quantity'), ('유통기한', 'expiry_date')]
    return export_to_excel(queryset, 'Inventory_List', columns)

@login_required
def export_purchase_excel(request):
    queryset = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    start_date = request.GET.get('start_date'); end_date = request.GET.get('end_date')
    supplier_id = request.GET.get('supplier'); status = request.GET.get('status')
    if start_date: queryset = queryset.filter(purchase_date__gte=start_date)
    if end_date: queryset = queryset.filter(purchase_date__lte=end_date)
    if supplier_id: queryset = queryset.filter(supplier_id=supplier_id)
    if status: queryset = queryset.filter(status=status)
    columns = [('매입번호', 'id'), ('공급사', 'supplier__name'), ('매입일자', 'purchase_date'), ('총금액', 'total_amount'), ('상태', 'get_status_display')]
    return export_to_excel(queryset, 'Purchase_List', columns)

@login_required
def export_order_excel(request):
    queryset = Order.objects.select_related('client').order_by('-order_date')
    start_date = request.GET.get('start_date'); end_date = request.GET.get('end_date')
    client_id = request.GET.get('client'); status = request.GET.get('status')
    if start_date: queryset = queryset.filter(order_date__date__gte=start_date)
    if end_date: queryset = queryset.filter(order_date__date__lte=end_date)
    if client_id: queryset = queryset.filter(client_id=client_id)
    if status: queryset = queryset.filter(status=status)
    columns = [('주문번호', 'id'), ('납품처', 'client__name'), ('주문일시', 'order_date'), ('매출액', 'total_revenue'), ('상태', 'get_status_display')]
    return export_to_excel(queryset, 'Order_List', columns)
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.db.models import Sum, Q  # <--- Q 확인
from django.db.models.functions import TruncDay
from datetime import timedelta
from django.http import HttpResponse
from django.template.loader import render_to_string
from decimal import Decimal
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator # <--- Paginator 확인
import weasyprint

# ---------------------------------------------------------
# [1] 모델 (Models)
# ---------------------------------------------------------
from .models import (
    Partner, Product, Purchase, PurchaseItem, Inventory, Order, OrderItem, 
    PickingList, Expense, Employee, Payroll, Payment, Zone, Location,
    CompanyInfo, BankAccount, BankTransaction, WorkLog, ProductCategory, StorageType, Notice
)

# ---------------------------------------------------------
# [2] 폼 (Forms)
# ---------------------------------------------------------
from .forms import (
    InboundForm, ProductForm, PartnerForm, 
    InventoryForm, PurchaseForm, OrderForm,
    ExpenseForm, EmployeeForm, PayrollForm, CompanyInfoForm,
    BankAccountForm, WorkLogForm, BankTransactionForm, SignUpForm,
    PurchaseCreateFormSet, OrderCreateFormSet, PaymentQuickForm,
    ZoneForm, LocationForm, NoticeForm
)

# ---------------------------------------------------------
# [3] 유틸리티 & 서비스 (Utils & Services)
# ---------------------------------------------------------
from .utils import generate_barcode_image, export_to_excel
from .services import create_picking_list


# =========================================================
#  SECTION 1: 인증 및 계정 (Auth)
# =========================================================
def signup(request):
    """회원가입"""
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
    """회원탈퇴"""
    if request.method == 'POST':
        user = request.user
        user.delete()
        return redirect('login')
    return render(request, 'registration/delete_account.html')


# =========================================================
#  SECTION 2: 대시보드 및 회사 설정 (Dashboard)
# =========================================================
@login_required
def dashboard(request):
    """메인 경영 대시보드"""
    today = timezone.now().date()
    this_month_start = today.replace(day=1)

    # 1. 금일 매출
    today_revenue = OrderItem.objects.filter(
        order__order_date__date=today, order__status='SHIPPED'
    ).aggregate(s=Sum('final_amount'))['s'] or 0

    # 2. 월간 실적 (매출, 원가, 비용, 이익)
    month_orders = Order.objects.filter(order_date__date__gte=this_month_start, status='SHIPPED')
    month_revenue = month_orders.aggregate(s=Sum('total_revenue'))['s'] or 0
    month_cogs = month_orders.aggregate(s=Sum('total_cogs'))['s'] or 0
    month_expenses = Expense.objects.filter(date__gte=this_month_start).aggregate(s=Sum('amount'))['s'] or 0
    month_profit = (month_revenue - month_cogs) - month_expenses

    # 3. 채권/채무
    partners = Partner.objects.all()
    total_receivable = 0
    total_payable = 0
    for p in partners:
        balance = p.current_balance
        if balance > 0: total_receivable += balance
        elif balance < 0: total_payable += abs(balance)

    # 4. 차트 데이터 (최근 7일 매출)
    last_7_days = today - timedelta(days=6)
    daily_sales_qs = Order.objects.filter(
        order_date__date__gte=last_7_days, status='SHIPPED'
    ).annotate(day=TruncDay('order_date')).values('day').annotate(total=Sum('total_revenue')).order_by('day')
    
    chart_dates = [d['day'].strftime('%m-%d') for d in daily_sales_qs]
    chart_revenues = [int(d['total']) for d in daily_sales_qs]

    # 5. 비용 차트
    expense_qs = Expense.objects.filter(date__gte=this_month_start).values('category').annotate(total=Sum('amount'))
    expense_labels = [ex['category'] for ex in expense_qs]
    expense_data = [int(ex['total']) for ex in expense_qs]

    # 6. 기타 알림
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

@login_required
def company_update(request):
    """회사 정보 설정"""
    company = CompanyInfo.objects.first()
    if not company: company = CompanyInfo.objects.create(name="우리회사(기본)")

    if request.method == 'POST':
        form = CompanyInfoForm(request.POST, instance=company)
        if form.is_valid(): form.save(); return redirect('fulfillment:dashboard')
    else: form = CompanyInfoForm(instance=company)
    return render(request, 'fulfillment/common_form.html', {'form': form, 'title': '🏢 우리 회사 정보 설정'})


# =========================================================
#  SECTION 3: 재고 및 입고 관리 (Inventory & Inbound)
# =========================================================
@login_required
def inbound_create(request):
    """입고 등록 (바코드 생성)"""
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
    """라벨 출력"""
    inv = get_object_or_404(Inventory, id=inventory_id)
    return render(request, 'fulfillment/print_label.html', {'inventory': inv, 'barcode_img': generate_barcode_image(inv.batch_number)})

@login_required
def inventory_list(request):
    """재고 리스트"""
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
def export_inventory_excel(request):
    """재고 엑셀 다운로드"""
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


# =========================================================
#  SECTION 4: 발주 및 매입 관리 (Purchases)
# =========================================================
@login_required
def purchase_list(request):
    """발주 리스트 및 신규 등록 팝업"""
    purchases = Purchase.objects.select_related('supplier').order_by('-purchase_date')
    start_date = request.GET.get('start_date'); end_date = request.GET.get('end_date')
    supplier_id = request.GET.get('supplier'); status = request.GET.get('status')

    if start_date: purchases = purchases.filter(purchase_date__gte=start_date)
    if end_date: purchases = purchases.filter(purchase_date__lte=end_date)
    if supplier_id: purchases = purchases.filter(supplier_id=supplier_id)
    if status: purchases = purchases.filter(status=status)

    suppliers = Partner.objects.filter(partner_type__in=['SUPPLIER', 'BOTH'])
    products_all = Product.objects.all()
    locations_all = Location.objects.filter(is_active=True)
    
    # 신규 등록용 폼 (팝업)
    form = PurchaseForm(initial={'purchase_date': timezone.now().date()})
    formset = PurchaseCreateFormSet(queryset=PurchaseItem.objects.none(), prefix='items') 

    context = {
        'purchases': purchases, 'suppliers': suppliers,
        'products_all': products_all, 'locations_all': locations_all,
        'form': form, 'formset': formset
    }
    return render(request, 'fulfillment/purchase_list.html', context)

@login_required
def purchase_create(request):
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseCreateFormSet(request.POST, prefix='items')
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


# =========================================================
#  SECTION 5: 주문 및 출고 관리 (Orders & Fulfillment)
# =========================================================
@login_required
def order_list(request):
    """주문 리스트 및 신규 등록 팝업"""
    orders = Order.objects.select_related('client').order_by('-order_date')
    start_date = request.GET.get('start_date'); end_date = request.GET.get('end_date')
    client_id = request.GET.get('client'); status = request.GET.get('status')

    if start_date: orders = orders.filter(order_date__date__gte=start_date)
    if end_date: orders = orders.filter(order_date__date__lte=end_date)
    if client_id: orders = orders.filter(client_id=client_id)
    if status: orders = orders.filter(status=status)

    clients = Partner.objects.filter(partner_type__in=['CLIENT', 'BOTH'])
    products_all = Product.objects.all()
    
    # 신규 등록용 폼 (팝업)
    form = OrderForm(initial={'status': 'PENDING'})
    formset = OrderCreateFormSet(queryset=OrderItem.objects.none(), prefix='items')

    context = {
        'orders': orders, 'clients': clients, 'products_all': products_all,
        'form': form, 'formset': formset
    }
    return render(request, 'fulfillment/order_list.html', context)

# fulfillment/views.py 의 해당 함수 교체

@login_required
def order_create(request):
    if request.method == 'POST':
        form = OrderForm(request.POST)
        formset = OrderCreateFormSet(request.POST, prefix='items')
        
        if form.is_valid() and formset.is_valid():
            order = form.save(commit=False)
            order.status = 'PENDING'
            order.save()
            
            items = formset.save(commit=False)
            total_rev = 0
            total_cost = 0 
            
            for item in items:
                item.order = order
                
                # ★ [핵심] 주문 시점의 상품 매입가를 '박제'합니다.
                # 나중에 상품 가격이 올라도, 이 item.cost_price는 변하지 않습니다.
                item.cost_price = item.product.purchase_price 
                
                # 매출액 계산 (판매가 x 수량)
                item.final_amount = item.quantity * item.product.price
                
                # 원가 누적 (박제된 원가 x 수량)
                total_cost += (item.cost_price * item.quantity)
                
                item.save()
                total_rev += item.final_amount
            
            # 주문서 합계 업데이트
            order.total_revenue = total_rev
            order.total_cogs = total_cost
            order.save()
            
            return redirect('fulfillment:order_list')
            
    return redirect('fulfillment:order_list')

@login_required
def order_update(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.method == 'POST':
        form = OrderForm(request.POST, instance=order)
        formset = OrderCreateFormSet(request.POST, instance=order)
        
        if form.is_valid() and formset.is_valid():
            order = form.save() # 1. 주문 기본 정보 저장
            
            # 2. 변경되거나 추가된 품목들 먼저 저장
            # (여기서 반환되는 items는 '변경된' 항목들뿐입니다. 변경 안 된 건 안 들어있음)
            updated_items = formset.save(commit=False)
            for item in updated_items:
                item.order = order
                # 수정 시점의 가격으로 업데이트
                item.cost_price = item.product.purchase_price 
                item.final_amount = item.quantity * item.product.price
                item.save()
            
            # 3. 삭제된 품목 처리
            for obj in formset.deleted_objects:
                obj.delete()
            
            # 4. ★ [핵심 수정] 합계 재계산 로직 변경
            # 방금 저장한 것뿐만 아니라, 기존에 있던(수정 안 한) 품목까지 
            # '모두' 불러와서 총액을 다시 계산해야 합니다.
            
            # DB에서 현재 주문에 속한 모든 아이템을 다시 조회
            all_items = order.items.all() 
            
            total_rev = 0
            total_cost = 0
            
            for item in all_items:
                # 혹시라도 계산이 안 된 항목이 있다면 방어적으로 계산 (데이터 무결성 보장)
                if item.final_amount == 0 and item.quantity > 0:
                     item.final_amount = item.quantity * item.product.price
                     item.cost_price = item.product.purchase_price # 원가도 없으면 채워넣기
                     item.save()
                
                total_rev += item.final_amount
                total_cost += (item.cost_price * item.quantity)
            
            # 5. 최종 주문서 합계 업데이트
            order.total_revenue = total_rev
            order.total_cogs = total_cost
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
def order_allocate(request, pk):
    """피킹 지시 (재고 할당)"""
    order = get_object_or_404(Order, pk=pk)
    try:
        create_picking_list(order)
        messages.success(request, f"주문 #{order.id} 피킹 지시 완료")
    except Exception as e:
        messages.error(request, f"오류: {e}")
    return redirect('fulfillment:order_list')

@login_required
def process_weight(request, order_id):
    """출고 계량 처리"""
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        if order.status == 'SHIPPED': return redirect('fulfillment:generate_invoice', order_id=order.id)
        
        for picking in order.picking_lists.all():
            w = request.POST.get(f'weight_{picking.id}')
            if w: 
                picking.picked_weight = float(w); picking.picked = True; picking.save()
        
        total_rev = 0; real_cogs = 0
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
    """거래 명세서"""
    order = get_object_or_404(Order, id=order_id)
    items = order.items.all()
    my_company = CompanyInfo.objects.first()
    if not my_company: my_company = CompanyInfo(name="(회사정보 미설정)")
    
    current_total = order.total_revenue
    total_balance = 0; previous_balance = 0
    if order.client:
        initial = order.client.initial_balance
        past_sales = Order.objects.filter(client=order.client, status='SHIPPED').filter(Q(order_date__lt=order.order_date)|Q(order_date=order.order_date, id__lt=order.id)).aggregate(s=Sum('total_revenue'))['s'] or 0
        total_paid = Payment.objects.filter(partner=order.client, payment_type='INBOUND', date__lte=order.order_date.date()).aggregate(s=Sum('amount'))['s'] or 0
        previous_balance = (initial + past_sales) - total_paid
        total_balance = previous_balance + current_total

    context = {
        'order': order, 'items': items, 'company': my_company,
        'today': timezone.now().date(), 'previous_balance': previous_balance, 'total_balance': total_balance,
    }
    return render(request, 'fulfillment/invoice_pdf.html', context)

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


# =========================================================
#  SECTION 6: 재무 및 회계 (Finance)
# =========================================================
@login_required
def monthly_report(request):
    """월간 손익 보고서"""
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


# =========================================================
#  SECTION 7: 인사 및 급여 (HR)
# =========================================================
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


# =========================================================
#  SECTION 8: 기초 정보 관리 (Master Data)
# =========================================================

# --- 8-1. 거래처 (Partners) ---
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
    """거래처 상세 원장 (매출/매입/수금/지급 통합 조회)"""
    partner = get_object_or_404(Partner, pk=pk)
    transactions = []
    
    # 1. 매출
    if partner.partner_type in ['CLIENT', 'BOTH']:
        orders = partner.order_set.filter(status='SHIPPED')
        for o in orders:
            o.data_type='order'; o.type_label="매출"; o.amount=o.total_revenue; o.date=o.order_date.date(); o.link_id=o.id
            transactions.append(o)
    # 2. 매입
    if partner.partner_type in ['SUPPLIER', 'BOTH']:
        purchases = partner.purchase_set.filter(status='RECEIVED')
        for p in purchases:
            p.data_type='purchase'; p.type_label="매입"; p.amount=p.total_amount; p.date=p.purchase_date; p.link_id=p.id
            transactions.append(p)
    # 3. 결제
    for pay in partner.payment_set.all():
        pay.data_type='payment'; pay.type_label=pay.get_payment_type_display(); pay.link_id=pay.id
        pay.calc_amount = -pay.amount
        transactions.append(pay)

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

# --- 8-2. 상품 (Products) ---
@login_required
def product_list(request):
    products = Product.objects.order_by('category', 'name')
    name_q = request.GET.get('name'); cat_q = request.GET.get('category'); sto_q = request.GET.get('storage')
    if name_q: products = products.filter(name__icontains=name_q)
    if cat_q: products = products.filter(category=cat_q)
    if sto_q: products = products.filter(storage_type=sto_q)
    form = ProductForm()
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

# --- 8-3. 창고/위치 (Locations) ---
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
    
@login_required
def print_partner_ledger(request, pk):
    """거래처 원장 인쇄용 페이지 (상품명 상세 표시 + 콤마 적용)"""
    partner = get_object_or_404(Partner, pk=pk)
    
    my_company = CompanyInfo.objects.first()
    if not my_company:
        my_company = CompanyInfo(name="(회사정보 미설정)", owner_name="-", address="-", phone="-")

    # 1. 조회 기간 설정
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    if start_date_str:
        start_date = timezone.datetime.strptime(start_date_str, '%Y-%m-%d').date()
    else:
        start_date = timezone.now().date().replace(day=1)

    if end_date_str:
        end_date = timezone.datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        end_date = timezone.now().date()

    # 2. 데이터 수집
    transactions = []

    # (1) 매출 (Client) - 상품명 가져오기
    if partner.partner_type in ['CLIENT', 'BOTH']:
        # prefetch_related를 써서 상품 정보를 미리 가져옵니다 (성능 최적화)
        orders = partner.order_set.filter(status='SHIPPED').prefetch_related('items__product')
        
        for o in orders:
            # 해당 주문의 모든 상품명 리스트 만들기
            item_names = [item.product.name for item in o.items.all()]
            
            if item_names:
                # 상품이 여러 개면 "사과, 배, 포도" 식으로 나열
                # 너무 길어질 경우를 대비해 20자 정도에서 자르거나, 지금처럼 다 보여주거나 선택 가능합니다.
                # 여기서는 상세하게 다 보여주는 방식으로 작성합니다.
                desc_text = ", ".join(item_names)
            else:
                desc_text = f"주문 #{o.id} (품목 없음)"
                
            transactions.append({
                'date': o.order_date.date(), 
                'type': '매출', 
                'desc': desc_text, # ★ 상품명으로 변경됨
                'amount': o.total_revenue, 
                'obj': o
            })

    # (2) 매입 (Supplier) - 상품명 가져오기
    if partner.partner_type in ['SUPPLIER', 'BOTH']:
        purchases = partner.purchase_set.filter(status='RECEIVED').prefetch_related('items__product')
        
        for p in purchases:
            item_names = [item.product.name for item in p.items.all()]
            
            if item_names:
                desc_text = ", ".join(item_names)
            else:
                desc_text = f"발주 #{p.id} (품목 없음)"

            transactions.append({
                'date': p.purchase_date, 
                'type': '매입', 
                'desc': desc_text, # ★ 상품명으로 변경됨
                'amount': p.total_amount, 
                'obj': p
            })

    # (3) 결제 (Payment)
    for pay in partner.payment_set.all():
        transactions.append({
            'date': pay.date, 
            'type': pay.get_payment_type_display(), 
            'desc': pay.memo or "(내용 없음)", # 결제는 메모를 표시
            'amount': -pay.amount, 
            'obj': pay
        })

    transactions.sort(key=lambda x: x['date'])

    # 3. 이월 잔액 계산 (기존 로직 동일)
    carry_over_balance = partner.initial_balance
    period_transactions = []
    period_total_sales = 0
    period_total_paid = 0

    for t in transactions:
        if t['date'] < start_date:
            carry_over_balance += t['amount']
        elif t['date'] <= end_date:
            if t['amount'] > 0: period_total_sales += t['amount']
            else: period_total_paid += abs(t['amount'])
            
            running_balance = carry_over_balance + period_total_sales - period_total_paid
            t['balance'] = running_balance
            period_transactions.append(t)
    
    final_balance = carry_over_balance + period_total_sales - period_total_paid

    context = {
        'partner': partner, 
        'company': my_company,
        'start_date': start_date, 'end_date': end_date,
        'carry_over_balance': carry_over_balance, 'transactions': period_transactions,
        'total_sales': period_total_sales, 'total_paid': period_total_paid,
        'final_balance': final_balance, 'today': timezone.now().date(),
    }
    return render(request, 'fulfillment/partner_ledger_print.html', context)
    
# ---------------------------------------------------------
#  SECTION 9: 공지사항 (Notice)
# ---------------------------------------------------------

@login_required
def notice_list(request):
    """공지사항 목록"""
    query = request.GET.get('q', '')
    # 중요 공지 먼저, 그 다음 최신순 정렬
    notices = Notice.objects.all().order_by('-is_important', '-created_at')
    
    if query:
        notices = notices.filter(Q(title__icontains=query) | Q(content__icontains=query))
    
    # 페이지네이션 (10개씩)
    paginator = Paginator(notices, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    form = NoticeForm() # 등록 팝업용 빈 폼
    
    return render(request, 'fulfillment/notice_list.html', {
        'notices': page_obj, 
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'form': form
    })

@login_required
def notice_create(request):
    """공지사항 등록"""
    if request.method == 'POST':
        form = NoticeForm(request.POST, request.FILES)
        if form.is_valid():
            notice = form.save(commit=False)
            notice.author = request.user
            notice.save()
            return redirect('fulfillment:notice_list')
    return redirect('fulfillment:notice_list')

@login_required
def notice_detail(request, pk):
    """공지사항 상세"""
    notice = get_object_or_404(Notice, pk=pk)
    # 조회수 증가 (본인이 쓴 글이 아닐 때만)
    if notice.author != request.user:
        notice.views += 1
        notice.save()
    return render(request, 'fulfillment/notice_detail.html', {'notice': notice})   
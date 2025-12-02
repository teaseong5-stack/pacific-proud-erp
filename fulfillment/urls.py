from django.urls import path
from . import views

app_name = 'fulfillment'

urlpatterns = [
    # 1. 대시보드
    path('', views.dashboard, name='dashboard'),

    # 2. 물류 프로세스
    path('inbound/', views.inbound_create, name='inbound_create'),
    path('label/<int:inventory_id>/', views.print_label, name='print_label'),
    path('order/<int:order_id>/weight/', views.process_weight, name='process_weight'),
    path('order/<int:order_id>/invoice/', views.generate_invoice_pdf, name='generate_invoice'),
    
    # 3. 리포트
    path('report/', views.monthly_report, name='monthly_report'),

    # 4. ERP 리스트 화면 (조회)
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('orders/', views.order_list, name='order_list'),
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('expenses/', views.expense_list, name='expense_list'),
    path('employees/', views.employee_list, name='employee_list'),
    path('payrolls/', views.payroll_list, name='payroll_list'),
    path('partners/', views.partner_list, name='partner_list'),
    path('products/', views.product_list, name='product_list'),

    # 5. 등록 처리 (팝업 연결용) ★ 여기가 중요합니다!
    path('products/create/', views.product_create, name='product_create'),
    path('partners/create/', views.partner_create, name='partner_create'), # 이 줄이 없어서 에러가 났습니다.
    # --- ★ 추가: 수정 및 삭제 URL ---
    # 1. 상품 (Product)
    path('products/update/<int:pk>/', views.product_update, name='product_update'),
    path('products/delete/<int:pk>/', views.product_delete, name='product_delete'),

    # 2. 거래처 (Partner)
    path('partners/update/<int:pk>/', views.partner_update, name='partner_update'),
    path('partners/delete/<int:pk>/', views.partner_delete, name='partner_delete'),
    
    # 재고 관리
    path('inventory/update/<int:pk>/', views.inventory_update, name='inventory_update'),
    path('inventory/delete/<int:pk>/', views.inventory_delete, name='inventory_delete'),

    # 매입 관리
    path('purchases/update/<int:pk>/', views.purchase_update, name='purchase_update'),
    path('purchases/delete/<int:pk>/', views.purchase_delete, name='purchase_delete'),

    # 주문 관리
    path('orders/update/<int:pk>/', views.order_update, name='order_update'),
    path('orders/delete/<int:pk>/', views.order_delete, name='order_delete'),
    # 회사 정보
    path('settings/company/', views.company_update, name='company_update'),
    # 비용
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/update/<int:pk>/', views.expense_update, name='expense_update'),
    path('expenses/delete/<int:pk>/', views.expense_delete, name='expense_delete'),

    # 직원
    path('employees/create/', views.employee_create, name='employee_create'),
    path('employees/update/<int:pk>/', views.employee_update, name='employee_update'),
    path('employees/delete/<int:pk>/', views.employee_delete, name='employee_delete'),

    # 급여
    path('payrolls/create/', views.payroll_create, name='payroll_create'),
    path('payrolls/update/<int:pk>/', views.payroll_update, name='payroll_update'),
    path('payrolls/delete/<int:pk>/', views.payroll_delete, name='payroll_delete'),
    
    path('purchases/create/', views.purchase_create, name='purchase_create'),
    path('orders/create/', views.order_create, name='order_create'),
    path('export/inventory/', views.export_inventory_excel, name='export_inventory'),
    path('export/purchase/', views.export_purchase_excel, name='export_purchase'),
    path('export/order/', views.export_order_excel, name='export_order'),
    
    # 인증 관련 (가입/탈퇴)
    path('signup/', views.signup, name='signup'),
    path('delete_account/', views.delete_account, name='delete_account'),
    
    # 통장 관리
    path('bank/', views.bank_list, name='bank_list'),
    path('bank/create/', views.bank_create, name='bank_create'),
    path('bank/<int:pk>/', views.bank_detail, name='bank_detail'),
    path('bank/transaction/create/', views.bank_transaction_create, name='bank_transaction_create'),

    # 업무 일지
    path('worklog/', views.worklog_list, name='worklog_list'),
    path('worklog/create/', views.worklog_create, name='worklog_create'),
    path('worklog/update/<int:pk>/', views.worklog_update, name='worklog_update'),
    path('worklog/delete/<int:pk>/', views.worklog_delete, name='worklog_delete'),
   ]
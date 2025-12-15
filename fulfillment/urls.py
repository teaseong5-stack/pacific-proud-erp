from django.urls import path
from . import views

app_name = 'fulfillment'

urlpatterns = [
    # ★ [핵심 수정] 메인 페이지('') 접속 시 대시보드로 연결
    path('', views.dashboard, name='index'), 

    # 1. 대시보드
    path('dashboard/', views.dashboard, name='dashboard'),

    # 2. 물류 (입고)
    path('inbound/', views.inbound_create, name='inbound_create'),
    path('label/<int:inventory_id>/', views.print_label, name='print_label'),

    # 3. 재고 관리 (+엑셀)
    path('inventory/', views.inventory_list, name='inventory_list'),
    path('inventory/update/<int:pk>/', views.inventory_update, name='inventory_update'),
    path('inventory/delete/<int:pk>/', views.inventory_delete, name='inventory_delete'),
    path('inventory/export/', views.export_inventory_excel, name='export_inventory_excel'),

    # 4. 발주/매입 (+엑셀)
    path('purchases/', views.purchase_list, name='purchase_list'),
    path('purchases/create/', views.purchase_create, name='purchase_create'),
    path('purchases/update/<int:pk>/', views.purchase_update, name='purchase_update'),
    path('purchases/delete/<int:pk>/', views.purchase_delete, name='purchase_delete'),
    path('purchases/export/', views.export_purchase_excel, name='export_purchase_excel'),

    # 5. 주문/출고 (+엑셀)
    path('orders/', views.order_list, name='order_list'),
    path('orders/create/', views.order_create, name='order_create'),
    path('orders/update/<int:pk>/', views.order_update, name='order_update'),
    path('orders/delete/<int:pk>/', views.order_delete, name='order_delete'),
    path('orders/export/', views.export_order_excel, name='export_order_excel'),
    
    # 주문 프로세스 (피킹 -> 중량 -> 명세서)
    path('order/<int:pk>/allocate/', views.order_allocate, name='order_allocate'),
    path('order/<int:order_id>/weight/', views.process_weight, name='process_weight'),
    path('order/<int:order_id>/invoice/', views.generate_invoice_pdf, name='generate_invoice'),

    # 6. 재무/회계
    path('report/monthly/', views.monthly_report, name='monthly_report'),
    path('expenses/', views.expense_list, name='expense_list'),
    path('expenses/create/', views.expense_create, name='expense_create'),
    path('expenses/update/<int:pk>/', views.expense_update, name='expense_update'),
    path('expenses/delete/<int:pk>/', views.expense_delete, name='expense_delete'),

    # 7. 인사/급여
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/create/', views.employee_create, name='employee_create'),
    path('employees/update/<int:pk>/', views.employee_update, name='employee_update'),
    path('employees/delete/<int:pk>/', views.employee_delete, name='employee_delete'),

    path('payrolls/', views.payroll_list, name='payroll_list'),
    path('payrolls/create/', views.payroll_create, name='payroll_create'),
    path('payrolls/update/<int:pk>/', views.payroll_update, name='payroll_update'),
    path('payrolls/delete/<int:pk>/', views.payroll_delete, name='payroll_delete'),

    path('worklogs/', views.worklog_list, name='worklog_list'),
    path('worklogs/create/', views.worklog_create, name='worklog_create'),
    path('worklogs/update/<int:pk>/', views.worklog_update, name='worklog_update'),
    path('worklogs/delete/<int:pk>/', views.worklog_delete, name='worklog_delete'),

    # 8. 기초정보 - 거래처
    path('partners/', views.partner_list, name='partner_list'),
    path('partners/create/', views.partner_create, name='partner_create'),
    path('partners/update/<int:pk>/', views.partner_update, name='partner_update'),
    path('partners/delete/<int:pk>/', views.partner_delete, name='partner_delete'),
    path('partners/<int:pk>/', views.partner_detail, name='partner_detail'),
    # 거래처 원장 출력
    path('partners/<int:pk>/ledger/print/', views.print_partner_ledger, name='print_partner_ledger'),
    
    # 거래처 입출금 (Payment)
    path('partners/<int:pk>/payment/create/', views.partner_payment_create, name='partner_payment_create'),
    path('payment/update/<int:pk>/', views.payment_update, name='payment_update'),
    path('payment/delete/<int:pk>/', views.payment_delete, name='payment_delete'),

    # 9. 기초정보 - 상품
    path('products/', views.product_list, name='product_list'),
    path('products/create/', views.product_create, name='product_create'),
    path('products/update/<int:pk>/', views.product_update, name='product_update'),
    path('products/delete/<int:pk>/', views.product_delete, name='product_delete'),

    # 10. 기초정보 - 회사 및 계좌
    path('settings/company/', views.company_update, name='company_update'),
    
    path('banks/', views.bank_list, name='bank_list'),
    path('banks/create/', views.bank_create, name='bank_create'),
    path('banks/transaction/create/', views.bank_transaction_create, name='bank_transaction_create'),
    path('banks/<int:pk>/', views.bank_detail, name='bank_detail'),

    # 11. 기초정보 - 창고/위치
    path('locations/', views.location_list, name='location_list'),
    path('zones/create/', views.zone_create, name='zone_create'),
    path('zones/delete/<int:pk>/', views.zone_delete, name='zone_delete'),
    path('locations/create/', views.location_create, name='location_create'),
    path('locations/delete/<int:pk>/', views.location_delete, name='location_delete'),
]
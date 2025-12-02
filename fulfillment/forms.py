from django import forms
from django.forms import inlineformset_factory  # ★ 이 줄이 꼭 있어야 합니다!
from .models import (
    Inventory, Product, Location, Partner, Purchase, PurchaseItem, 
    Order, OrderItem, Employee, Payroll, Expense, Payment, CompanyInfo)
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User    

# 1. 물류/재고 폼
class InboundForm(forms.ModelForm):
    """입고 등록 폼 (UI 개선용)"""
    class Meta:
        model = Inventory
        fields = ['product', 'location', 'quantity', 'expiry_date']
        widgets = {
            'product': forms.Select(attrs={
                'class': 'form-select search-select', # select2 적용
                'data-placeholder': '상품을 검색하세요 (이름 또는 SKU)',
                'style': 'width: 100%;'
            }),
            'location': forms.Select(attrs={
                'class': 'form-select search-select',
                'data-placeholder': '적치 위치 선택',
                'style': 'width: 100%;'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg fw-bold text-end', # 크고 굵게
                'placeholder': '0',
                'min': '1'
            }),
            'expiry_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'form-control form-control-lg text-center'
            }),
        }

class InventoryForm(forms.ModelForm):
    class Meta:
        model = Inventory
        fields = ['product', 'location', 'quantity', 'expiry_date', 'batch_number']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select'}),
            'location': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'batch_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

# 2. 기초 정보 폼
class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'sku', 'category', 'storage_type', 'unit', 'purchase_price', 'price', 'shelf_life_days', 'is_taxable']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'storage_type': forms.Select(attrs={'class': 'form-select'}),
            'unit': forms.TextInput(attrs={'class': 'form-control'}),
            'purchase_price': forms.NumberInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
            'shelf_life_days': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_taxable': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PartnerForm(forms.ModelForm):
    class Meta:
        model = Partner
        fields = ['name', 'partner_type', 'biz_number', 'owner_name', 'phone', 'address', 'contact_person', 'contact_phone', 'initial_balance']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'partner_type': forms.Select(attrs={'class': 'form-select'}),
            'biz_number': forms.TextInput(attrs={'class': 'form-control'}),
            'owner_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_person': forms.TextInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'initial_balance': forms.NumberInput(attrs={'class': 'form-control'}),
        }

class CompanyInfoForm(forms.ModelForm):
    class Meta:
        model = CompanyInfo
        fields = ['name', 'biz_number', 'ceo_name', 'phone', 'address', 'bank_account']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'biz_number': forms.TextInput(attrs={'class': 'form-control'}),
            'ceo_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'bank_account': forms.TextInput(attrs={'class': 'form-control'}),
        }

# 3. 인사/급여/재무 폼
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date', 'category', 'description', 'amount', 'has_proof']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'has_proof': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ['name', 'department', 'position', 'base_salary', 'join_date', 'resignation_date', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'department': forms.TextInput(attrs={'class': 'form-control'}),
            'position': forms.TextInput(attrs={'class': 'form-control'}),
            'base_salary': forms.NumberInput(attrs={'class': 'form-control'}),
            'join_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'resignation_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class PayrollForm(forms.ModelForm):
    class Meta:
        model = Payroll
        fields = ['payment_date', 'month_label', 'employee', 'base_pay', 'bonus', 'leave_pay', 'deduction']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'month_label': forms.TextInput(attrs={'class': 'form-control'}),
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'base_pay': forms.NumberInput(attrs={'class': 'form-control'}),
            'bonus': forms.NumberInput(attrs={'class': 'form-control'}),
            'leave_pay': forms.NumberInput(attrs={'class': 'form-control'}),
            'deduction': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# 4. 발주/주문 (헤더 및 폼셋)
class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'purchase_date', 'status', 'is_bill_published']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'purchase_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_bill_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class OrderForm(forms.ModelForm):
    """주문 수정 폼"""
    class Meta:
        model = Order
        fields = ['client', 'status', 'memo'] # ★ memo 추가됨
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'memo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '배송 요청사항 등 메모 입력'}),
        }

# ★ 아래 폼셋(FormSet) 정의가 반드시 있어야 합니다!
class PurchaseItemForm(forms.ModelForm):
    class Meta:
        model = PurchaseItem
        fields = ['product', 'quantity', 'target_location', 'expiry_date']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control'}),
            'target_location': forms.Select(attrs={'class': 'form-select'}),
            'expiry_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

PurchaseCreateFormSet = inlineformset_factory(
    Purchase, PurchaseItem, form=PurchaseItemForm,
    extra=5, can_delete=True
)

class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select', 'onchange': 'updateRow(this)'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity-input', 'oninput': 'updateRow(this)'}),
        }

OrderCreateFormSet = inlineformset_factory(
    Order, OrderItem, form=OrderItemForm,
    extra=5, can_delete=True
)

class SignUpForm(UserCreationForm):
    """회원가입 폼 (Bootstrap 적용)"""
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name'] # ID, 이메일, 이름 입력
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 모든 필드에 부트스트랩 스타일 적용
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'
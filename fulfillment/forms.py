from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import (
    Inventory, Product, Location, Partner, Purchase, PurchaseItem, 
    Order, OrderItem, Employee, Payroll, Expense, Payment, CompanyInfo,
    BankAccount, BankTransaction, WorkLog, Zone
)

# --- 회원가입 폼 ---
class SignUpForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'form-control'

# --- 물류 폼 ---
class InboundForm(forms.ModelForm):
    product = forms.ModelChoiceField(queryset=Product.objects.all(), widget=forms.Select(attrs={'class': 'form-select search-select'}))
    location = forms.ModelChoiceField(queryset=Location.objects.filter(is_active=True), widget=forms.Select(attrs={'class': 'form-select search-select'}))
    quantity = forms.IntegerField(widget=forms.NumberInput(attrs={'class': 'form-control'}))
    expiry_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    class Meta:
        model = Inventory
        fields = ['product', 'location', 'quantity', 'expiry_date']

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

# --- 기초 정보 폼 ---
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

# --- 재무/인사 폼 ---
class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ['date', 'category', 'description', 'amount', 'has_proof', 'payment_account']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'has_proof': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'payment_account': forms.Select(attrs={'class': 'form-select'}),
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

# --- 자금/업무일지 폼 (★ BankTransactionForm 포함) ---
class BankAccountForm(forms.ModelForm):
    class Meta:
        model = BankAccount
        fields = ['bank_name', 'account_number', 'account_holder', 'initial_balance', 'is_active']
        widgets = {
            'bank_name': forms.TextInput(attrs={'class': 'form-control'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control'}),
            'account_holder': forms.TextInput(attrs={'class': 'form-control'}),
            'initial_balance': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class BankTransactionForm(forms.ModelForm):
    class Meta:
        model = BankTransaction
        fields = ['bank_account', 'date', 'transaction_type', 'amount', 'description']
        widgets = {
            'bank_account': forms.Select(attrs={'class': 'form-select'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'transaction_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
        }

class WorkLogForm(forms.ModelForm):
    class Meta:
        model = WorkLog
        fields = ['date', 'employee', 'content', 'issues']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'employee': forms.Select(attrs={'class': 'form-select'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'issues': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

# --- 발주/주문 폼셋 ---
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
PurchaseCreateFormSet = inlineformset_factory(Purchase, PurchaseItem, form=PurchaseItemForm, extra=5, can_delete=True)

class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['client', 'status', 'memo']
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'memo': forms.TextInput(attrs={'class': 'form-control'}),
        }
class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ['product', 'quantity']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-select product-select', 'onchange': 'updateRow(this)'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control quantity-input', 'oninput': 'updateRow(this)'}),
        }
OrderCreateFormSet = inlineformset_factory(Order, OrderItem, form=OrderItemForm, extra=5, can_delete=True)

class ZoneForm(forms.ModelForm):
    """창고 구역 등록 폼"""
    class Meta:
        model = Zone
        fields = ['name', 'storage_type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: A구역 냉동고'}),
            'storage_type': forms.Select(attrs={'class': 'form-select'}),
        }

class LocationForm(forms.ModelForm):
    """세부 위치 등록 폼"""
    class Meta:
        model = Location
        fields = ['zone', 'code', 'is_active']
        widgets = {
            'zone': forms.Select(attrs={'class': 'form-select'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '예: A-01-01'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
class PaymentQuickForm(forms.ModelForm):
    """거래처 상세 화면용 간편 입출금 폼"""
    class Meta:
        model = Payment
        fields = ['date', 'payment_type', 'amount', 'method', 'memo']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'payment_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '금액 입력'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'memo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '적요 (예: 11월분 결제)'}),
        }        
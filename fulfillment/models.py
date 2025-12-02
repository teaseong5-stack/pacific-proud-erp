from django.db import models
from django.utils import timezone
from django.db.models import Sum

# --- 1. 기초 정보 (Enum 정의) ---
class StorageType(models.TextChoices):
    DRY = 'DRY', '상온 (Dry)'
    COLD = 'COLD', '냉장 (Cold)'
    FROZEN = 'FROZEN', '냉동 (Frozen)'
    LIVE_TANK = 'LIVE_TANK', '활어 수조 (Live Tank)'

class ProductCategory(models.TextChoices):
    SEAFOOD = 'SEAFOOD', '수산물'
    MEAT = 'MEAT', '육류'
    LIQUOR = 'LIQUOR', '주류'
    INDUSTRIAL = 'INDUSTRIAL', '공산품'
    DAILY = 'DAILY', '생필품'
    VEGETABLE = 'VEGETABLE', '농산물'

class PartnerType(models.TextChoices):
    SUPPLIER = 'SUPPLIER', '매입처'
    CLIENT = 'CLIENT', '매출처'
    BOTH = 'BOTH', '혼합'

class ExpenseCategory(models.TextChoices):
    SALARY = 'SALARY', '급여/인건비'
    RENT = 'RENT', '임차료'
    UTILITY = 'UTILITY', '수도광열비'
    LOGISTICS = 'LOGISTICS', '운반비'
    MEAL = 'MEAL', '복리후생비'
    TAX = 'TAX', '세금과공과'
    ETC = 'ETC', '기타'

# --- 2. 자금 관리 (통장) ★ 순서 상단 이동! ---
class BankAccount(models.Model):
    """법인 통장 계좌"""
    bank_name = models.CharField(max_length=50, verbose_name="은행명")
    account_number = models.CharField(max_length=50, verbose_name="계좌번호")
    account_holder = models.CharField(max_length=50, verbose_name="예금주", default="(주)퍼시픽프라우드")
    initial_balance = models.DecimalField(max_digits=15, decimal_places=0, default=0, verbose_name="기초 잔액")
    is_active = models.BooleanField(default=True, verbose_name="사용 중")

    def __str__(self):
        return f"{self.bank_name} ({self.account_number})"

    @property
    def current_balance(self):
        in_total = self.transactions.filter(transaction_type='DEPOSIT').aggregate(s=Sum('amount'))['s'] or 0
        out_total = self.transactions.filter(transaction_type='WITHDRAWAL').aggregate(s=Sum('amount'))['s'] or 0
        return self.initial_balance + in_total - out_total

# Expense 모델은 BankTransaction과 서로 참조하므로 문자열 참조('Expense')를 사용해야 함
class BankTransaction(models.Model):
    """통장 입출금 내역"""
    TYPE_CHOICES = [('DEPOSIT', '입금'), ('WITHDRAWAL', '출금')]
    bank_account = models.ForeignKey(BankAccount, on_delete=models.CASCADE, related_name='transactions', verbose_name="계좌")
    date = models.DateField(default=timezone.now, verbose_name="거래일")
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES, verbose_name="구분")
    amount = models.DecimalField(max_digits=15, decimal_places=0, verbose_name="금액")
    description = models.CharField(max_length=100, verbose_name="적요")
    related_expense = models.OneToOneField('Expense', on_delete=models.SET_NULL, null=True, blank=True, related_name='bank_trx')

    def __str__(self):
        return f"[{self.get_transaction_type_display()}] {self.amount} - {self.description}"

# --- 3. 거래처 및 창고 ---
class Partner(models.Model):
    name = models.CharField(max_length=100, verbose_name="상호명")
    partner_type = models.CharField(max_length=10, choices=PartnerType.choices, verbose_name="구분")
    biz_number = models.CharField(max_length=20, verbose_name="사업자번호", blank=True, null=True)
    owner_name = models.CharField(max_length=50, verbose_name="대표자명", blank=True, null=True)
    phone = models.CharField(max_length=20, verbose_name="대표 전화번호", blank=True, null=True)
    address = models.CharField(max_length=200, verbose_name="주소", blank=True, null=True)
    contact_person = models.CharField(max_length=50, verbose_name="담당자명", blank=True, null=True)
    contact_phone = models.CharField(max_length=20, verbose_name="담당자 연락처", blank=True, null=True)
    initial_balance = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="기초 미수/미지급금")

    def __str__(self):
        return f"[{self.get_partner_type_display()}] {self.name}"

    @property
    def current_balance(self):
        if self.partner_type == 'CLIENT':
            total_trade = self.order_set.filter(status='SHIPPED').aggregate(s=Sum('total_revenue'))['s'] or 0
            total_paid = self.payment_set.aggregate(s=Sum('amount'))['s'] or 0
            return (self.initial_balance + total_trade) - total_paid
        elif self.partner_type == 'SUPPLIER':
            total_trade = self.purchase_set.filter(status='RECEIVED').aggregate(s=Sum('total_amount'))['s'] or 0
            total_paid = self.payment_set.aggregate(s=Sum('amount'))['s'] or 0
            return (self.initial_balance + total_trade) - total_paid
        return 0

class Zone(models.Model):
    name = models.CharField(max_length=50)
    storage_type = models.CharField(max_length=20, choices=StorageType.choices, default=StorageType.DRY)
    def __str__(self): return self.name

class Location(models.Model):
    zone = models.ForeignKey(Zone, on_delete=models.CASCADE, related_name='locations')
    code = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.code

# --- 4. 상품 (Product) ---
class Product(models.Model):
    sku = models.CharField(max_length=50, unique=True)
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=20, choices=ProductCategory.choices, default=ProductCategory.SEAFOOD)
    storage_type = models.CharField(max_length=20, choices=StorageType.choices)
    unit = models.CharField(max_length=10, default='EA')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    price = models.DecimalField(max_digits=10, decimal_places=0)
    shelf_life_days = models.IntegerField(default=7)
    is_taxable = models.BooleanField(default=True)
    def __str__(self): return self.name

# --- 5. 매입/재고 ---
class Purchase(models.Model):
    supplier = models.ForeignKey(Partner, on_delete=models.PROTECT, limit_choices_to={'partner_type__in': ['SUPPLIER', 'BOTH']})
    purchase_date = models.DateField(default=timezone.now)
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    status = models.CharField(max_length=20, default='ORDERED', choices=[('ORDERED','발주됨'), ('RECEIVED','입고완료')])
    is_bill_published = models.BooleanField(default=False)
    def __str__(self): return f"매입 #{self.id}"

class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=0)
    target_location = models.ForeignKey(Location, on_delete=models.PROTECT)
    expiry_date = models.DateField()
    def save(self, *args, **kwargs):
        if not self.unit_cost: self.unit_cost = self.product.purchase_price
        super().save(*args, **kwargs)

class Inventory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = models.IntegerField(default=0)
    batch_number = models.CharField(max_length=50)
    received_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField()
    @property
    def is_expired(self): return self.expiry_date < timezone.now().date()
    def __str__(self): return f"{self.product.name} ({self.quantity})"

# --- 6. 매출/주문 ---
class Order(models.Model):
    client = models.ForeignKey(Partner, on_delete=models.PROTECT, limit_choices_to={'partner_type__in': ['CLIENT', 'BOTH']}, null=True)
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('PENDING', '접수'), ('ALLOCATED', '피킹지시'), ('SHIPPED', '출고완료')], default='PENDING')
    memo = models.CharField(max_length=200, blank=True, null=True)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    total_cogs = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    def __str__(self): return f"주문 #{self.id}"
    @property
    def gross_profit(self): return self.total_revenue - self.total_cogs

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    supplied_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    final_amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    def save(self, *args, **kwargs):
        if self.supplied_weight and self.product.unit.lower() in ['kg', 'g']:
             self.final_amount = self.supplied_weight * self.product.price
        elif not self.final_amount:
             self.final_amount = self.quantity * self.product.price
        super().save(*args, **kwargs)

class PickingList(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='picking_lists')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE)
    allocated_qty = models.IntegerField()
    picked = models.BooleanField(default=False)
    picked_weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

# --- 7. 재무/회계 (Expense) ★ BankAccount 참조 가능! ---
class Expense(models.Model):
    date = models.DateField(default=timezone.now, verbose_name="지출일자")
    category = models.CharField(max_length=20, choices=ExpenseCategory.choices, verbose_name="계정과목")
    description = models.CharField(max_length=100, verbose_name="적요 (내용)")
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="지출금액")
    has_proof = models.BooleanField(default=True, verbose_name="적격증빙 유무")
    payment_account = models.ForeignKey(BankAccount, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="출금 계좌")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.payment_account:
            if hasattr(self, 'bank_trx') and self.bank_trx:
                self.bank_trx.bank_account = self.payment_account
                self.bank_trx.date = self.date
                self.bank_trx.amount = self.amount
                self.bank_trx.description = f"[지출] {self.description}"
                self.bank_trx.save()
            else:
                BankTransaction.objects.create(
                    bank_account=self.payment_account, date=self.date, transaction_type='WITHDRAWAL',
                    amount=self.amount, description=f"[지출] {self.description}", related_expense=self
                )
    def __str__(self): return f"[{self.get_category_display()}] {self.description}"

# --- 8. 인사/급여 (HR) ---
class Employee(models.Model):
    name = models.CharField(max_length=50)
    position = models.CharField(max_length=50)
    department = models.CharField(max_length=50, default="물류팀")
    join_date = models.DateField()
    resignation_date = models.DateField(null=True, blank=True)
    base_salary = models.DecimalField(max_digits=12, decimal_places=0)
    is_active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Payroll(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT)
    payment_date = models.DateField(default=timezone.now)
    month_label = models.CharField(max_length=20)
    base_pay = models.DecimalField(max_digits=12, decimal_places=0)
    bonus = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    leave_pay = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    deduction = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)
    related_expense = models.OneToOneField(Expense, on_delete=models.SET_NULL, null=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        self.total_amount = (self.base_pay + self.bonus + self.leave_pay) - self.deduction
        super().save(*args, **kwargs)
        
        description = f"급여 지급 - {self.employee.name} ({self.month_label})"
        if self.related_expense:
            self.related_expense.amount = self.total_amount
            self.related_expense.date = self.payment_date
            self.related_expense.description = description
            self.related_expense.save()
        else:
            exp = Expense.objects.create(date=self.payment_date, category=ExpenseCategory.SALARY, description=description, amount=self.total_amount, has_proof=True)
            self.related_expense = exp
            super().save(update_fields=['related_expense'])

class Payment(models.Model):
    PAYMENT_TYPE = [('INBOUND', '수금'), ('OUTBOUND', '지급')]
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    method = models.CharField(max_length=20, default='CASH', choices=[('CASH','현금'), ('BANK','계좌'), ('CARD','카드')])
    memo = models.CharField(max_length=100, blank=True)
    def __str__(self): return f"{self.partner.name} - {self.amount}"

class WorkLog(models.Model):
    date = models.DateField(default=timezone.now)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    content = models.TextField()
    issues = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"{self.date} - {self.employee.name}"

class CompanyInfo(models.Model):
    name = models.CharField(max_length=100, default="우리회사")
    biz_number = models.CharField(max_length=20, blank=True)
    ceo_name = models.CharField(max_length=50, blank=True)
    address = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    bank_account = models.CharField(max_length=100, blank=True)
    def save(self, *args, **kwargs):
        if not self.pk and CompanyInfo.objects.exists():
            self.pk = CompanyInfo.objects.first().pk
        super().save(*args, **kwargs)
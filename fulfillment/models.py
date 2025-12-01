from django.db import models
from django.utils import timezone
from django.db.models import Sum

# --- 1. 기초 정보 (Enum) ---
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

# --- 2. 기초 모델 ---
class Partner(models.Model):
    """거래처 관리 (CRM/SRM)"""
    name = models.CharField(max_length=100, verbose_name="상호명")
    partner_type = models.CharField(max_length=10, choices=PartnerType.choices, verbose_name="구분")
    biz_number = models.CharField(max_length=20, verbose_name="사업자번호", blank=True, null=True)
    owner_name = models.CharField(max_length=50, verbose_name="대표자명", blank=True, null=True)
    phone = models.CharField(max_length=20, verbose_name="대표 전화번호", blank=True, null=True)
    address = models.CharField(max_length=200, verbose_name="주소", blank=True, null=True)
    
    # ★ 추가된 필드: 실무 담당자 정보
    contact_person = models.CharField(max_length=50, verbose_name="담당자명", blank=True, null=True)
    contact_phone = models.CharField(max_length=20, verbose_name="담당자 연락처", blank=True, null=True)
    
    initial_balance = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="기초 미수/미지급금")

    def __str__(self):
        return f"[{self.get_partner_type_display()}] {self.name}"

    @property
    def current_balance(self):
        # (기존 잔액 계산 로직 그대로 유지)
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

# --- 3. 매입/재고 ---
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

# --- 4. 매출/주문 (여기가 에러 원인!) ---
class Order(models.Model):
    """주문 헤더"""
    client = models.ForeignKey(Partner, on_delete=models.PROTECT, limit_choices_to={'partner_type__in': ['CLIENT', 'BOTH']}, verbose_name="납품처", null=True)
    order_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=[('PENDING', '접수'), ('ALLOCATED', '피킹지시'), ('SHIPPED', '출고완료')], default='PENDING')
    
    # ★ 추가된 필드: 주문 메모
    memo = models.CharField(max_length=200, blank=True, null=True, verbose_name="주문 메모")

    # 손익 분석용 스냅샷 필드
    total_revenue = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="총 매출액")
    total_cogs = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="총 원가(COGS)")

    def __str__(self):
        client_name = self.client.name if self.client else "미지정"
        return f"주문 #{self.id} - {client_name}"

    @property
    def gross_profit(self):
        return self.total_revenue - self.total_cogs

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

# --- 5. 비용 & 인사 & 자금 ---
class Expense(models.Model):
    date = models.DateField(default=timezone.now)
    category = models.CharField(max_length=20, choices=ExpenseCategory.choices)
    description = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    has_proof = models.BooleanField(default=True)
    def __str__(self): return f"{self.description}"

# --- 7. 인사/급여 (HR) ---
class Employee(models.Model):
    """직원 정보"""
    name = models.CharField(max_length=50, verbose_name="성명")
    position = models.CharField(max_length=50, verbose_name="직급")
    department = models.CharField(max_length=50, verbose_name="부서", default="물류팀")
    join_date = models.DateField(verbose_name="입사일")
    # ★ 이 부분이 빠져서 에러가 난 것입니다!
    resignation_date = models.DateField(verbose_name="퇴사일", null=True, blank=True)
    
    base_salary = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="기본급 (VND)")
    is_active = models.BooleanField(default=True, verbose_name="재직 여부")

    def __str__(self):
        return f"{self.name} ({self.position})"

class Payroll(models.Model):
    """월 급여 대장"""
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, verbose_name="직원")
    payment_date = models.DateField(default=timezone.now, verbose_name="지급일")
    month_label = models.CharField(max_length=20, verbose_name="귀속월")
    
    # 급여 상세
    base_pay = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="기본급")
    bonus = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="성과급")
    # ★ 이 부분도 추가되어야 합니다!
    leave_pay = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="수당(년/월차)")
    deduction = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="차감액(세금/보험)")
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0, verbose_name="실수령액")
    
    # 회계 자동 연동
    related_expense = models.OneToOneField('Expense', on_delete=models.SET_NULL, null=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        # 실수령액 자동 계산
        self.total_amount = (self.base_pay + self.bonus + self.leave_pay) - self.deduction
        super().save(*args, **kwargs)
        
        # 비용 자동 생성/수정 로직
        from .models import Expense, ExpenseCategory
        description = f"급여 지급 - {self.employee.name} ({self.month_label})"
        
        if self.related_expense:
            self.related_expense.amount = self.total_amount
            self.related_expense.date = self.payment_date
            self.related_expense.description = description
            self.related_expense.save()
        else:
            exp = Expense.objects.create(
                date=self.payment_date, 
                category=ExpenseCategory.SALARY, 
                description=description, 
                amount=self.total_amount, 
                has_proof=True
            )
            self.related_expense = exp
            super().save(update_fields=['related_expense'])

    def __str__(self):
        return f"{self.employee.name} - {self.month_label}"

class Payment(models.Model):
    PAYMENT_TYPE = [('INBOUND', '수금'), ('OUTBOUND', '지급')]
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE)
    amount = models.DecimalField(max_digits=12, decimal_places=0)
    method = models.CharField(max_length=20, default='CASH', choices=[('CASH','현금'), ('BANK','계좌'), ('CARD','카드')])
    memo = models.CharField(max_length=100, blank=True)
    def __str__(self): return f"{self.partner.name} - {self.amount}"
    
class CompanyInfo(models.Model):
    """우리 회사 정보 (명세서 출력용)"""
    name = models.CharField(max_length=100, verbose_name="상호명", default="우리회사")
    biz_number = models.CharField(max_length=20, verbose_name="사업자번호", blank=True)
    ceo_name = models.CharField(max_length=50, verbose_name="대표자명", blank=True)
    address = models.CharField(max_length=200, verbose_name="사업장 주소", blank=True)
    phone = models.CharField(max_length=20, verbose_name="대표 전화", blank=True)
    bank_account = models.CharField(max_length=100, verbose_name="입금 계좌번호", blank=True, help_text="예: 국민은행 000-000-000000")

    def save(self, *args, **kwargs):
        # 데이터가 1개만 존재하도록 강제함 (싱글톤 패턴 흉내)
        if not self.pk and CompanyInfo.objects.exists():
            # 이미 데이터가 있으면, 기존 것의 ID를 가져와서 덮어쓰기
            self.pk = CompanyInfo.objects.first().pk
        super().save(*args, **kwargs)

    def __str__(self):
        return "우리 회사 정보"    
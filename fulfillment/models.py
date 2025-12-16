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
    """비용 계정과목 정의"""
    # ★ 추가된 항목: 물품대금
    PURCHASE = 'PURCHASE', '물품대금 (매입)' 
    
    SALARY = 'SALARY', '급여/인건비'
    RENT = 'RENT', '임차료'
    UTILITY = 'UTILITY', '수도광열비 (전기/수도)'
    LOGISTICS = 'LOGISTICS', '운반비/물류비'
    MEAL = 'MEAL', '복리후생비 (식대 등)'
    TAX = 'TAX', '세금과공과'
    ETC = 'ETC', '기타 잡비'

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
    email = models.EmailField(verbose_name="이메일", blank=True, null=True)

    def __str__(self):
        return f"[{self.get_partner_type_display()}] {self.name}"

    @property
    def current_balance(self):
        """
        현재 잔액 계산 (실시간)
        - CLIENT(매출처): (기초 + 매출총액) - 입금총액 = 받을 돈 (양수)
        - SUPPLIER(매입처): (기초 + 매입총액) - 출금총액 = 줄 돈 (양수 -> 음수로 표현하여 부채임을 표시)
        """
        # 1. 입출금 내역 집계
        deposit_total = self.payment_set.filter(payment_type='INBOUND').aggregate(s=Sum('amount'))['s'] or 0
        withdrawal_total = self.payment_set.filter(payment_type='OUTBOUND').aggregate(s=Sum('amount'))['s'] or 0
        
        if self.partner_type == 'CLIENT':
            # 매출 총액 (출고완료 기준)
            sales_total = self.order_set.filter(status='SHIPPED').aggregate(s=Sum('total_revenue'))['s'] or 0
            # (기초 + 매출) - (받은돈 - 거스름돈?) -> 보통 수금만 있음
            return (self.initial_balance + sales_total) - deposit_total
            
        elif self.partner_type == 'SUPPLIER':
            # 매입 총액 (입고완료 기준) -> ★ 여기서 매입대금이 집계됩니다.
            purchase_total = self.purchase_set.filter(status='RECEIVED').aggregate(s=Sum('total_amount'))['s'] or 0
            
            # 줄 돈(매입액)에서 준 돈(출금)을 뺌. 
            # 결과가 양수면 '줄 돈이 남았다(미지급금)'는 뜻.
            # ERP 상에서는 미지급금을 '음수(-)'로 표현하여 자산과 구분하기도 함.
            # 여기서는 [줄 돈 - 준 돈] 으로 계산하여, 양수면 빚이 있는 것.
            payable = (self.initial_balance + purchase_total) - withdrawal_total
            
            # 대시보드 합산을 위해 '미지급금'은 음수로 반환하는 것이 계산상 편함 (자산 감소)
            return payable * -1 

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
    # ★ 추가된 메서드: 총금액 업데이트
    def update_total_amount(self):
        # 연결된 모든 아이템의 (수량*단가) 합계
        total = self.items.aggregate(
            total=Sum(models.F('quantity') * models.F('unit_cost'), output_field=models.DecimalField())
        )['total'] or 0
        self.total_amount = total
        self.save()

class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=0)
    target_location = models.ForeignKey(Location, on_delete=models.PROTECT)
    expiry_date = models.DateField()
    def save(self, *args, **kwargs):
        # 1. 단가 자동 설정
        if not self.unit_cost:
            self.unit_cost = self.product.purchase_price
        
        super().save(*args, **kwargs)
        
        # 2. ★ 저장 후 부모(Purchase)의 총금액 재계산 (트리거)
        self.purchase.update_total_amount()

    def delete(self, *args, **kwargs):
        # 3. 삭제 시에도 총금액 재계산
        purchase = self.purchase
        super().delete(*args, **kwargs)
        purchase.update_total_amount()

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
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    cost_price = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="주문당시 매입가")
    supplied_weight = models.FloatField(null=True, blank=True)
    final_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    def __str__(self):
        return f"{self.order.id} - {self.product.name}"
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
    """자금 입출금 내역 (거래처 원장)"""
    PAYMENT_TYPE = [
        ('INBOUND', '수금 (입금)'),   # 매출처에서 돈 받음 -> 통장 잔액 증가
        ('OUTBOUND', '지급 (출금)'),  # 매입처에 돈 줌 -> 통장 잔액 감소
    ]
    
    partner = models.ForeignKey('Partner', on_delete=models.CASCADE, verbose_name="거래처")
    date = models.DateField(default=timezone.now, verbose_name="거래일자")
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE, verbose_name="구분")
    amount = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="금액")
    method = models.CharField(max_length=20, default='CASH', choices=[('CASH','현금'), ('BANK','계좌이체'), ('CARD','카드')], verbose_name="결제수단")
    memo = models.CharField(max_length=100, blank=True, verbose_name="적요")
    
    # ★ 추가됨: 연동할 법인 계좌
    bank_account = models.ForeignKey('BankAccount', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="연동 계좌")
    
    # 내부적으로 생성된 BankTransaction을 추적하기 위한 필드 (선택사항, 1:1 연결)
    related_bank_trx = models.OneToOneField('BankTransaction', on_delete=models.SET_NULL, null=True, blank=True, editable=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # 계좌가 선택되었다면 -> 통장 내역(BankTransaction) 자동 생성/수정
        if self.bank_account:
            # 1. 거래 유형 결정 (Partner Payment 기준 -> Bank 기준 변환)
            # 수금(INBOUND) -> 통장에선 입금(DEPOSIT)
            # 지급(OUTBOUND) -> 통장에선 출금(WITHDRAWAL)
            trx_type = 'DEPOSIT' if self.payment_type == 'INBOUND' else 'WITHDRAWAL'
            
            # 적요 자동 생성 (예: [수금] 강남포차)
            desc = f"[{self.get_payment_type_display()}] {self.partner.name}"
            if self.memo:
                desc += f" - {self.memo}"

            if self.related_bank_trx:
                # 이미 연결된 내역이 있으면 업데이트
                self.related_bank_trx.bank_account = self.bank_account
                self.related_bank_trx.date = self.date
                self.related_bank_trx.transaction_type = trx_type
                self.related_bank_trx.amount = self.amount
                self.related_bank_trx.description = desc
                self.related_bank_trx.save()
            else:
                # 없으면 새로 생성
                # BankTransaction 모델을 가져와야 함 (문자열 참조 회피)
                from .models import BankTransaction 
                
                trx = BankTransaction.objects.create(
                    bank_account=self.bank_account,
                    date=self.date,
                    transaction_type=trx_type,
                    amount=self.amount,
                    description=desc
                )
                self.related_bank_trx = trx
                # 다시 저장 (연결 정보 업데이트)
                super().save(update_fields=['related_bank_trx'])

    def __str__(self):
        return f"[{self.get_payment_type_display()}] {self.partner.name} - {self.amount}"

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
        
# ★ [추가] 공지사항 모델
class Notice(models.Model):
    title = models.CharField(max_length=200, verbose_name="제목")
    content = models.TextField(verbose_name="내용")
    author = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="작성자")
    is_important = models.BooleanField(default=False, verbose_name="중요 공지(상단고정)")
    file = models.FileField(upload_to='notices/', null=True, blank=True, verbose_name="첨부파일")
    views = models.PositiveIntegerField(default=0, verbose_name="조회수")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="작성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    def __str__(self):
        return self.title        
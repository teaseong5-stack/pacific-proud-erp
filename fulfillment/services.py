from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Inventory, PickingList

def create_picking_list(order):
    """
    주문을 받아 FEFO 원칙으로 피킹 리스트를 생성하고,
    ★ 재고를 실시간으로 차감(점유)합니다.
    """
    with transaction.atomic():
        # 이미 처리된 주문이면 패스
        if order.status != 'PENDING':
            return

        for item in order.items.all():
            qty_needed = item.quantity
            product = item.product

            # FEFO: 유통기한 임박순으로 재고 찾기
            candidates = Inventory.objects.filter(
                product=product, 
                quantity__gt=0
            ).order_by('expiry_date', 'received_date')

            # 재고가 아예 없으면 에러
            if not candidates.exists():
                raise ValidationError(f"'{product.name}'의 재고가 없습니다.")

            for stock in candidates:
                if qty_needed <= 0:
                    break

                take_qty = min(qty_needed, stock.quantity)

                # 피킹 리스트 생성 (작업 지시서)
                PickingList.objects.create(
                    order=order,
                    inventory=stock,
                    allocated_qty=take_qty
                )

                # ★★★ 핵심: 여기서 재고를 차감합니다! (선점) ★★★
                stock.quantity -= take_qty
                stock.save()

                qty_needed -= take_qty

            # 재고가 부족해서 다 못 채운 경우 에러 발생
            if qty_needed > 0:
                raise ValidationError(f"'{product.name}' 재고가 부족합니다. (부족수량: {qty_needed})")

        # 상태 변경: 접수(PENDING) -> 피킹지시(ALLOCATED)
        order.status = 'ALLOCATED'
        order.save()
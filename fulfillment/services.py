from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Inventory, PickingList

def create_picking_list(order):
    """
    주문을 받아 FEFO 원칙으로 피킹 리스트를 생성하고,
    ★ 상태가 ALLOCATED(피킹지시)로 될 때 실재고를 미리 차감합니다.
    """
    with transaction.atomic():
        # 이미 할당된 주문이면 중복 실행 방지
        if order.status != 'PENDING':
            return

        for item in order.items.all():
            qty_needed = item.quantity
            product = item.product

            # FEFO: 유통기한 임박순 정렬
            candidates = Inventory.objects.filter(
                product=product, 
                quantity__gt=0
            ).order_by('expiry_date', 'received_date')

            for stock in candidates:
                if qty_needed <= 0:
                    break

                take_qty = min(qty_needed, stock.quantity)

                # 피킹 리스트 생성
                PickingList.objects.create(
                    order=order,
                    inventory=stock,
                    allocated_qty=take_qty
                )

                # ★★★ 핵심 수정: 여기서 재고를 바로 차감합니다! ★★★
                stock.quantity -= take_qty
                stock.save()

                qty_needed -= take_qty

            # 재고 부족 시 에러 발생 (선택 사항: 에러 대신 부분 할당을 원하면 이 부분 수정 가능)
            if qty_needed > 0:
                raise ValidationError(f"'{product.name}' 재고가 부족합니다. (부족수량: {qty_needed})")

        # 상태 변경: 접수 -> 피킹지시
        order.status = 'ALLOCATED'
        order.save()
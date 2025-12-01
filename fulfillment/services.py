from django.db import transaction
from django.core.exceptions import ValidationError
from .models import Inventory, PickingList

def create_picking_list(order):
    """
    주문(Order)을 받아 FEFO(유통기한 임박순) 원칙으로 재고를 찾아 
    피킹 리스트를 생성하고 재고를 차감(점유)하는 함수
    """
    
    # 데이터 무결성을 위해 트랜잭션 처리 (도중에 에러나면 전체 롤백)
    with transaction.atomic():
        if order.status != 'PENDING':
            # 이미 처리된 주문이면 그냥 종료
            return

        for item in order.items.all():
            qty_needed = item.quantity
            product = item.product

            # 핵심 로직: 해당 상품의 재고를 가져오되, '유통기한 오름차순'으로 정렬 (FEFO)
            candidates = Inventory.objects.filter(
                product=product, 
                quantity__gt=0
            ).order_by('expiry_date', 'received_date')

            for stock in candidates:
                if qty_needed <= 0:
                    break

                # 이 배치에서 가져갈 수 있는 수량 계산
                take_qty = min(qty_needed, stock.quantity)

                # 피킹 리스트 생성 (작업 지시)
                PickingList.objects.create(
                    order=order,
                    inventory=stock,
                    allocated_qty=take_qty
                )

                # 재고 차감
                stock.quantity -= take_qty
                stock.save()

                qty_needed -= take_qty

            # 반복문을 다 돌았는데도 필요한 수량이 남았다면? -> 재고 부족!
            if qty_needed > 0:
                raise ValidationError(f"'{product.name}' 재고가 부족합니다. (부족수량: {qty_needed})")

        # 모든 아이템 할당 성공 시 상태 변경
        order.status = 'ALLOCATED'
        order.save()
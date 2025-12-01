from django.contrib import admin
from django.urls import path, include  # 1. include를 꼭 가져와야 합니다.

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 2. 따옴표 안에 아무것도 없는 '' 경로가 바로 '첫 화면'을 뜻합니다.
    # 이 줄이 있어야 로켓 화면이 사라지고 대시보드가 나옵니다.
    path('', include('fulfillment.urls')), 
]
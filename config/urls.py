from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 1. 관리자 페이지
    path('admin/', admin.site.urls),
    
    # 2. 인증 URL (로그인, 로그아웃 등)
    path('accounts/', include('django.contrib.auth.urls')),
    
    # 3. 메인 ERP 앱 (fulfillment)
    path('', include('fulfillment.urls')),
]
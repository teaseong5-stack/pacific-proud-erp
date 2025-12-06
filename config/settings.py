from pathlib import Path
import os
import dj_database_url # 추가

# 1. BASE_DIR 정의 (이 부분이 없어서 에러가 난 것입니다)
BASE_DIR = Path(__file__).resolve().parent.parent

# 2. 보안 키 (개발용 임의 키)
SECRET_KEY = 'django-insecure-test-key-for-food-erp'

# 3. 디버그 모드 (개발 중엔 True)
DEBUG = True

ALLOWED_HOSTS = ['*']

# 4. 앱 등록 (fulfillment 앱 필수!)
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'fulfillment',
    'django.contrib.humanize',  # <--- 콤마(,)가 뒤에 꼭 있어야 합니다!
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware', # ★ 여기에 추가!
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'], # 루트 템플릿 폴더 연결
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# 5. 데이터베이스 (기본 SQLite)
DATABASES = {
    'default': dj_database_url.config(
        default='sqlite:///' + os.path.join(BASE_DIR, 'db.sqlite3'),
        conn_max_age=600
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# 6. 언어 및 시간 설정 (한국)
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_I18N = True
USE_TZ = False # 직관적 관리를 위해 False 설정

# 7. 정적 파일 경로
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# 8. 기본 ID 필드 설정
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 로그인 성공 시 이동할 URL (대시보드)
LOGIN_REDIRECT_URL = '/'

# 로그아웃 시 이동할 URL (로그인 화면)
LOGOUT_REDIRECT_URL = '/accounts/login/'

# 이메일 설정 (Gmail)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = 'pacificproud.dn@gmail.com'
EMAIL_HOST_PASSWORD = ' thaibinhduong123*$' # 띄어쓰기 없이 입력
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
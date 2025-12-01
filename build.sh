#!/usr/bin/env bash
# exit on error
set -o errexit

# 1. 패키지 설치
pip install -r requirements.txt

# 2. 정적 파일(CSS/JS) 모으기
python manage.py collectstatic --no-input

# 3. 데이터베이스 마이그레이션 (서버 DB 최신화)
python manage.py migrate
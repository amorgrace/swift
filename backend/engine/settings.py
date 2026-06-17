import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / '.env')

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
try:
    SECRET_KEY = os.environ['SECRET_KEY']
except KeyError:
    raise RuntimeError(
        'The SECRET_KEY environment variable is not set. '
        'Add SECRET_KEY to backend/.env or your environment.'
    )

DEBUG = os.environ['DEBUG'].lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = os.environ['ALLOWED_HOSTS'].split(',')

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'ninja_jwt',
    'ninja_jwt.token_blacklist',
    'corsheaders',
    'anymail',
    'authenticator',
    'rates',
    'wallets',
    'transactions',
    'kyc',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'engine.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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

WSGI_APPLICATION = 'engine.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=0,
            ssl_require=True,
        )
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = 'authenticator.User'

AUTH_PASSWORD_VALIDATORS = []

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# JWT (ninja-jwt)
# ---------------------------------------------------------------------------
NINJA_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# ---------------------------------------------------------------------------
# Email (Mailtrap via Anymail)
# ---------------------------------------------------------------------------
MAILTRAP_API_TOKEN = os.environ['MAILTRAP_API_TOKEN']
DEFAULT_FROM_EMAIL = os.environ['DEFAULT_FROM_EMAIL']
FRONTEND_URL = os.environ['FRONTEND_URL']

EMAIL_BACKEND = "anymail.backends.mailtrap.EmailBackend"
ANYMAIL = {
    "MAILTRAP_API_TOKEN": MAILTRAP_API_TOKEN,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = os.environ['CORS_ALLOWED_ORIGINS'].split(',')

# ---------------------------------------------------------------------------
# Quidax, Paystack, CoinGecko, Conversion Settings
# ---------------------------------------------------------------------------
QUIDAX_API_KEY = os.environ.get('QUIDAX_API_KEY', '')
QUIDAX_BASE_URL = os.environ.get('QUIDAX_API_BASE_URL', os.environ.get('QUIDAX_BASE_URL', 'https://openapi.quidax.io/exchange-open-api/api/v1'))

PAYSTACK_SECRET_KEY = os.environ.get('PAYSTACK_SECRET_KEY', '')
PAYSTACK_BASE_URL = os.environ.get('PAYSTACK_BASE_URL', 'https://api.paystack.co')

COINGECKO_API_KEY = os.environ.get('COINGECKO_API_KEY', '')
COINGECKO_BASE_URL = os.environ.get('COINGECKO_BASE_URL', 'https://api.coingecko.com/api/v3')

CONVERSION_MARGIN_PERCENTAGE = float(os.environ.get('CONVERSION_MARGIN_PERCENTAGE', '2.0'))
MIN_WITHDRAWAL_NGN = float(os.environ.get('MIN_WITHDRAWAL_NGN', '1000'))

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {name} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'authenticator': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'anymail': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


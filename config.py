from dotenv import load_dotenv
import os

# Загрузка переменных окружения из .env файла
load_dotenv()

BOT_TOKEN = os.environ.get('BOT_TOKEN')
SECRET = os.environ.get('SECRET')
ADMIN_ID = os.environ.get('ADMIN_ID')
GEONAMES_USERNAME = os.environ.get('GEONAMES')
TOMTOM_API_KEY = os.environ.get('TOMTOM_API_KEY')

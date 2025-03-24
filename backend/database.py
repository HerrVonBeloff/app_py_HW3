import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Загружаем переменные окружения из .env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in environment variables!")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

import redis
import os

# Получаем URL Redis из переменных окружения
REDIS_URL = os.getenv("REDIS_URL")

if not REDIS_URL:
    raise ValueError("❌ Переменная окружения REDIS_URL не установлена!")

# Подключаемся к Redis
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

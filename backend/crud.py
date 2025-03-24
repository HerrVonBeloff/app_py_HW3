from sqlalchemy.orm import Session
import models, schemas
import random
import string
from datetime import datetime, timedelta
import pytz
from database import redis_client
from datetime import timezone


MOSCOW_TZ = pytz.timezone("Europe/Moscow")

def generate_short_code(length: int = 6) -> str:
    """Генерация случайного короткого кода."""
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

def create_link(db: Session, link: schemas.LinkCreate, user: models.User = None) -> models.Link:
    """Создание ссылки. Временные ссылки (24 ч) для анонимных, вечные — только если указано is_permanent=True."""
    
    if link.is_permanent and not user:
        raise ValueError("Вечные ссылки могут создавать только авторизованные пользователи")
    
    if not user:  # Если пользователь не авторизован, создаем временную ссылку на 24 часа
        link.is_permanent = False
        link.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    
    elif user and link.is_permanent is None:  # Если пользователь авторизован, но is_permanent не указан → ссылка временная
        link.is_permanent = False
        link.expires_at = datetime.now(timezone.utc) + timedelta(days=1)

    short_code = link.custom_alias.strip() if link.custom_alias else generate_short_code()
    existing_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    if existing_link:
        raise ValueError(f"Код '{short_code}' уже существует!")

    db_link = models.Link(
        original_url=link.original_url,
        short_code=short_code,
        created_at=datetime.now(timezone.utc),
        expires_at=link.expires_at.astimezone(timezone.utc) if link.expires_at else None,
        is_permanent=link.is_permanent,
        owner_id=user.id if user else None,
        last_accessed=datetime.now(timezone.utc),
        clicks=0
    )

    db.add(db_link)
    db.commit()
    db.refresh(db_link)
    return db_link





def get_link_by_short_code(db: Session, short_code: str) -> models.Link | None:
    """Получение ссылки с кэшированием"""
    
    cached_url = redis_client.get(f"link:{short_code}")
    if cached_url:
        print(f"✅ Кэш найден для {short_code}")
        return db.query(models.Link).filter(models.Link.short_code == short_code).first()

    return db.query(models.Link).filter(models.Link.short_code == short_code).first()


def delete_link(db: Session, short_code: str, user: models.User) -> models.Link | None:
    """Удаление ссылки + очистка кэша"""
    link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    if not link:
        raise ValueError("Ссылка не найдена")

    if link.owner_id is not None and link.owner_id != user.id:
        raise ValueError("Нет прав")

    db.delete(link)
    db.commit()

    redis_client.delete(f"link:{short_code}")
    return link

def get_user_links(db: Session, user_id: int) -> list[models.Link]:
    return db.query(models.Link).filter(models.Link.owner_id == user_id).all()

def update_link(db: Session, short_code: str, new_url: str = None, expires_at: datetime = None) -> models.Link | None:
    """Обновление URL или срока жизни ссылки"""

    db_link = db.query(models.Link).filter(models.Link.short_code == short_code).first()
    if not db_link:
        return None

    if new_url:
        db_link.original_url = new_url

    if expires_at:
        db_link.expires_at = expires_at  # ✅ Теперь срок истечения можно менять много раз

    db.commit()
    db.refresh(db_link)

    redis_client.delete(f"link:{short_code}")  # Очистка кэша
    return db_link


def increment_clicks(db: Session, short_code: str) -> models.Link | None:
    """Обновление счетчика переходов и времени последнего доступа."""
    db_link = get_link_by_short_code(db, short_code)
    if db_link:
        db_link.clicks += 1
        db_link.last_accessed = datetime.now(timezone.utc)
        db.commit()
        db.refresh(db_link)
    return db_link

def delete_expired_links(db: Session) -> None:
    """Удаление:
    1. Временных ссылок с истекшим сроком
    2. Ссылок без активности >7 дней
    """
    now = datetime.now(MOSCOW_TZ)
    
    # Удаление по сроку действия
    time_expired = db.query(models.Link).filter(
        (models.Link.is_permanent == False) &
        (models.Link.expires_at < now)
    ).all()
    
    # Удаление по неактивности
    inactive_links = db.query(models.Link).filter(
        models.Link.last_accessed < (now - timedelta(days=7))
    ).all()
    
    for link in time_expired + inactive_links:
        db.delete(link)
    
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise
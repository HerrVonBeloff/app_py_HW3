import asyncio
import auth
import crud, models, schemas
import uvicorn

from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from database import SessionLocal, engine
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from contextlib import asynccontextmanager
from schemas import *
from database import redis_client
from datetime import datetime, timedelta


print("🚀 FastAPI успешно запущен!")

models.Base.metadata.create_all(bind=engine)

# SECRET_KEY = "your-secret-key"
# ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Код выполняется при запуске приложения
    with SessionLocal() as db:
        crud.delete_expired_links(db)
    
    # Запускаем фоновую задачу
    task = asyncio.create_task(periodic_cleanup())
    
    yield  # Здесь приложение работает
    
    # Код выполняется при завершении работы
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    token: Optional[str] = None,
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    if not token:  
        return None  # ✅ Теперь анонимный пользователь поддерживается

    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            return None
    except (JWTError, KeyError, TypeError): 
        return None

    return db.query(models.User).filter(models.User.username == username).first()





@app.post("/links/shorten", response_model=schemas.Link)
def create_short_link(
    link: schemas.LinkCreate,
    db: Session = Depends(get_db),
    current_user: Optional[models.User] = Depends(get_current_user)
):
    """Создание ссылки. Временные (24 ч) для анонимных, вечные — если is_permanent=True у авторизованных."""
    
    # Если пользователь анонимный, он может создать ТОЛЬКО временную ссылку на 24 часа
    if not current_user:
        link.is_permanent = False
        link.expires_at = datetime.now() + timedelta(days=1)
    else:
        if link.is_permanent is False: 
            link.expires_at = datetime.now() + timedelta(days=1)

    return crud.create_link(db, link, user=current_user)



@app.get("/{short_code}")
def redirect_to_original(short_code: str, db: Session = Depends(get_db)):
    """Перенаправление по короткой ссылке с кэшированием"""

    # Проверяем, есть ли в кэше
    cached_url = redis_client.get(f"link:{short_code}")
    if cached_url:
        print(f"✅ Кэш найден для {short_code}")
        return RedirectResponse(url=cached_url)

    # Если нет, берем из БД и кэшируем
    link = crud.get_link_by_short_code(db, short_code)
    if link is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")

    redis_client.setex(f"link:{short_code}", 3600, link.original_url)
    return RedirectResponse(url=link.original_url)

@app.delete("/links/{short_code}")
def delete_short_link(
    short_code: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Авторизация обязательна
):
    link = crud.get_link_by_short_code(db, short_code)
    if link is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    
    if link.owner_id is not None and link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы не можете удалить эту ссылку")
    
    crud.delete_link(db, short_code, current_user)  # Удаляем ссылку
    return {"message": "Ссылка удалена"}


@app.put("/links/{short_code}")
def update_short_link(
    short_code: str,
    original_url: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)  # Авторизация обязательна
):
    link = crud.get_link_by_short_code(db, short_code)
    if link is None:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")

    if link.owner_id is not None and link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы не можете изменить эту ссылку")

    updated_link = crud.update_link(db, short_code, original_url)
    return updated_link


@app.get("/links/{short_code}/stats", response_model=schemas.Link)
def get_link_stats(short_code: str, db: Session = Depends(get_db)):
    return crud.get_link_by_short_code(db, short_code) or HTTPException(status_code=404, detail="Ссылка не найдена")



@app.get("/links/{short_code}/original")
def get_original_url(short_code: str, db: Session = Depends(get_db)):
    """Находит оригинальный URL по короткому коду."""
    link = crud.get_link_by_short_code(db, short_code)
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")
    return {"original_url": link.original_url}



@app.post("/register", response_model=schemas.User)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(models.User).filter(
        (models.User.email == user.email) |
        (models.User.username == user.username)
    ).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    
    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    return db_user

@app.post("/token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(
        models.User.username == form_data.username
    ).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    return {
        "access_token": auth.create_access_token({"sub": user.username}),
        "token_type": "bearer"
    }

@app.post("/links/{short_code}/set_expiry")
def set_link_expiry(
    short_code: str,
    data: LinkExpiryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    expires_at = data.expires_at

    link = crud.get_link_by_short_code(db, short_code)
    if not link:
        raise HTTPException(status_code=404, detail="Ссылка не найдена")

    if not current_user or link.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Вы не можете изменить эту ссылку")


    expires_at = expires_at.replace(tzinfo=None)

    # Обновляем дату истечения
    link.expires_at = expires_at
    db.commit()
    db.refresh(link)

    # Удаляем старый кэш в Redis
    redis_client.delete(f"link:{short_code}")

    return {"message": "Срок действия ссылки обновлен", "expires_at": expires_at}



async def periodic_cleanup():
    """Периодическая очистка каждые 5 минут"""
    while True:
        await asyncio.sleep(300)  # 5 минут
        with SessionLocal() as db:
            crud.delete_expired_links(db)

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="debug")

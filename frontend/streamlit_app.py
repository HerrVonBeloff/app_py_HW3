import streamlit as st
import requests
from datetime import datetime, timedelta
import pytz

# --- Настройки ---
API_BASE_URL = "https://app-py-hw3.onrender.com"
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# --- Стилизация ---
st.set_page_config(page_title="Сервис сокращения ссылок", page_icon="🔗", layout="wide")
st.title("🔗 Умный (или не очень) сервис сокращения ссылок")

st.markdown("---")

# --- Функции ---
def get_auth_headers() -> dict:
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}

def format_datetime(dt_str: str | None) -> str:
    if not dt_str:
        return "Не ограничено"
    dt = datetime.fromisoformat(dt_str)
    return dt.astimezone(MOSCOW_TZ).strftime("%d.%m.%Y %H:%M:%S (МСК)")

# --- Авторизация ---
st.sidebar.header("🔐 Авторизация")
if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.current_user = None

if st.session_state.token:
    st.sidebar.success(f"Вы вошли как: {st.session_state.current_user}")
    if st.sidebar.button("Выйти"):
        st.session_state.token = None
        st.session_state.current_user = None
        st.rerun()
else:
    tab_login, tab_register = st.sidebar.tabs(["Вход", "Регистрация"])
    with tab_login:
        username = st.text_input("Логин", key="login_username")
        password = st.text_input("Пароль", type="password", key="login_password")
        if st.button("Войти"):
            try:
                response = requests.post(f"{API_BASE_URL}/token", data={"username": username, "password": password})
                response.raise_for_status()
                st.session_state.token = response.json()["access_token"]
                st.session_state.current_user = username
                st.rerun()
            except requests.exceptions.RequestException as e:
                st.error(f"Ошибка авторизации: {e.response.json().get('detail', 'Неверные учетные данные')}")
    
    with tab_register:
        new_username = st.text_input("Новый логин", key="register_username")
        new_email = st.text_input("Email", key="register_email")
        new_password = st.text_input("Пароль", type="password", key="register_password")
        if st.button("Зарегистрироваться"):
            try:
                response = requests.post(
                    f"{API_BASE_URL}/register", 
                    json={"username": new_username, "email": new_email, "password": new_password}
                )
                response.raise_for_status()
                st.success("✅ Регистрация успешна! Теперь войдите.")
            except requests.exceptions.RequestException as e:
                error_detail = e.response.json().get('detail', 'Ошибка регистрации')
                st.error(f"Ошибка регистрации: {error_detail}")

# --- Основная форма создания ссылки ---
st.subheader("✨ Создать короткую ссылку")
with st.form("create_form"):
    original_url = st.text_input("Введите длинную ссылку", placeholder="https://example.com")
    custom_alias = st.text_input("Кастомный код (опционально)", placeholder="myalias")
    is_permanent = st.checkbox(
        "Сделать вечной (доступно только авторизованным пользователям)", 
        value=False, 
        disabled=not st.session_state.token
    )
    
    if st.form_submit_button("Создать"):
        if not original_url:
            st.error("Пожалуйста, введите URL")
            st.stop()
            
        try:
            data = {
                "original_url": original_url,
                "custom_alias": custom_alias if custom_alias else None,
                "is_permanent": is_permanent if st.session_state.token else None
            }
            
            response = requests.post(
                f"{API_BASE_URL}/links/shorten", 
                json=data, 
                headers=get_auth_headers()
            )
            response.raise_for_status()
            
            response_data = response.json()
            short_code = response_data.get("short_code")
            if not short_code:
                raise ValueError("Ответ API не содержит short_code")
                
            short_url = f"{API_BASE_URL}/{short_code}"
            st.success(f"✅ Создана ссылка: [{short_url}]({short_url})")
            
        except requests.exceptions.HTTPError as e:
            error_detail = e.response.json().get('detail', 'Неизвестная ошибка')
            if "уже существует" in error_detail.lower() or "already exists" in error_detail.lower():
                st.error("❌ Этот короткий код уже используется. Пожалуйста, выберите другой.")
            elif "неверные учетные данные" in error_detail.lower():
                st.error("❌ Требуется авторизация для этого действия")
            else:
                st.error(f"❌ Ошибка при создании ссылки: {error_detail}")
                
        except Exception as e:
            st.error(f"❌ Произошла непредвиденная ошибка: {str(e)}")

# --- Блок управления ссылками ---
with st.expander("📋 Управление ссылками"):
    # 🔍 Найти оригинальную ссылку
    st.subheader("🔍 Найти оригинальную ссылку по короткому коду")
    with st.form("search_original_form"):
        search_code = st.text_input("Введите короткий код", key="search_code")
        if st.form_submit_button("🔎 Найти"):
            try:
                response = requests.get(f"{API_BASE_URL}/links/{search_code}/original")
                response.raise_for_status()
                data = response.json()
                st.success(f"🔗 Оригинальная ссылка: [{data['original_url']}]({data['original_url']})")
            except requests.exceptions.HTTPError:
                st.error("❌ Ссылка не найдена")
            except Exception as e:
                st.error(f"❌ Ошибка при поиске: {str(e)}")

    # 📊 Статистика ссылки
    st.subheader("📊 Статистика ссылки")
    with st.form("stats_form"):
        stats_code = st.text_input("Короткий код для статистики", key="stats_code")
        if st.form_submit_button("Показать статистику"):
            try:
                response = requests.get(f"{API_BASE_URL}/links/{stats_code}/stats")
                response.raise_for_status()
                data = response.json()
                st.markdown(f"""
                **📊 Статистика ссылки:** {stats_code}
                - 🔗 **Оригинальная ссылка:** [{data['original_url']}]({data['original_url']})
                - 📅 **Создана:** {format_datetime(data['created_at'])}
                - ⏳ **Истекает:** {format_datetime(data['expires_at'])}
                - 🔀 **Последний переход:** {format_datetime(data['last_accessed'])}
                - 🔢 **Количество переходов:** {data['clicks']}
                """)
            except requests.exceptions.HTTPError:
                st.error("❌ Ссылка не найдена")
            except Exception as e:
                st.error(f"❌ Ошибка при получении статистики: {str(e)}")

st.markdown("---")
st.markdown("🔔 **Важно:** Ссылки удаляются автоматически, если не используются в течение 7 дней.")
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
            response = requests.post(f"{API_BASE_URL}/token", data={"username": username, "password": password})
            if response.status_code == 200:
                st.session_state.token = response.json()["access_token"]
                st.session_state.current_user = username
                st.rerun()
            else:
                st.error("Ошибка авторизации")
    with tab_register:
        new_username = st.text_input("Новый логин", key="register_username")
        new_email = st.text_input("Email", key="register_email")
        new_password = st.text_input("Пароль", type="password", key="register_password")
        if st.button("Зарегистрироваться"):
            response = requests.post(f"{API_BASE_URL}/register", json={"username": new_username, "email": new_email, "password": new_password})
            if response.status_code == 200:
                st.success("✅ Регистрация успешна! Теперь войдите.")
            else:
                st.error("Ошибка регистрации")
                
# --- Основная форма создания ссылки ---
st.subheader("✨ Создать короткую ссылку")
with st.form("create_form"):
    original_url = st.text_input("Введите длинную ссылку")
    custom_alias = st.text_input("Кастомный код (опционально)")
    is_permanent = st.checkbox("Сделать вечной (доступно только авторизованным пользователям)", value=False, disabled=not st.session_state.token)
    if st.form_submit_button("Создать"):
        data = {
        "original_url": original_url,
        "custom_alias": custom_alias,
        "is_permanent": is_permanent if st.session_state.token else False
        }

        st.write("Отправляем в API:", data)
        st.write(get_auth_headers())
        response = requests.post(f"{API_BASE_URL}/links/shorten", json=data, headers=get_auth_headers())
        if response.status_code in [200, 201]:
            response_data = response.json()
            short_code = response_data.get("short_code")
            if not short_code:
                raise ValueError("Ответ не содержит short_code")
            short_url = f"{API_BASE_URL}/{short_code}"
            st.success(f"✅ Создана ссылка: [{short_url}]({short_url})")
        else:
            error_message = response.json().get("detail") or response.text
            st.error(f"Ошибка API: {error_message}")

# --- Блок управления ссылками ---
with st.expander("📋 Управление ссылками"):
    # 🔍 Найти оригинальную ссылку
    st.subheader("🔍 Найти оригинальную ссылку по короткому коду")
    with st.form("search_original_form"):
        search_code = st.text_input("Введите короткий код")
        if st.form_submit_button("🔎 Найти"):
            response = requests.get(f"{API_BASE_URL}/links/{search_code}/original")
            if response.status_code == 200:
                data = response.json()
                st.success(f"🔗 Оригинальная ссылка: [{data['original_url']}]({data['original_url']})")
            else:
                st.error("Ссылка не найдена")

    # 📊 Статистика ссылки
    st.subheader("📊 Статистика ссылки")
    with st.form("stats_form"):
        stats_code = st.text_input("Короткий код для статистики")
        if st.form_submit_button("Показать статистику"):
            response = requests.get(f"{API_BASE_URL}/links/{stats_code}/stats")
            if response.status_code == 200:
                data = response.json()
                st.markdown(f"""
                **📊 Статистика ссылки:** {stats_code}
                - 🔗 **Оригинальная ссылка:** [{data['original_url']}]({data['original_url']})
                - 📅 **Создана:** {format_datetime(data['created_at'])}
                - ⏳ **Истекает:** {format_datetime(data['expires_at'])}
                - 🔀 **Последний переход:** {format_datetime(data['last_accessed'])}
                - 🔢 **Количество переходов:** {data['clicks']}
                """)
            else:
                st.error("Ссылка не найдена")

st.markdown("---")
st.markdown("🔔 **Важно:** Ссылки удаляются автоматически, если не используются в течение 7 дней.")

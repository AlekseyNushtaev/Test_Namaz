from app.services.models import Session, User, create_tables, engine, Base
from sqlalchemy import select, update, inspect
from logger import logger

# Город по умолчанию – теперь просто кортеж данных
DEFAULT_CITY = (
    'Москва, Центральный федеральный округ, Россия',
    55.7504461,
    37.6174943,
    3
)


async def init_db(force: bool = False):
    """Инициализация БД: создание таблиц (данные по умолчанию не вставляются, так как нет отдельной таблицы городов)."""
    if force:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await create_tables()


async def set_user_city(user_id: int, city_name: str, lat: float, lon: float, tz: int) -> None:
    """
    Сохраняет или обновляет город пользователя.
    Если пользователь уже существует – обновляет его поля, иначе создаёт новую запись.
    """
    async with Session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        user.city_name = city_name
        user.latitude = lat
        user.longitude = lon
        user.timezone = tz

        await session.commit()


async def add_user(user_id: int) -> tuple:
    async with Session() as session:
        user = User(
            user_id=user_id,
            city_name=DEFAULT_CITY[0],
            latitude=DEFAULT_CITY[1],
            longitude=DEFAULT_CITY[2],
            timezone=DEFAULT_CITY[3]
        )
        session.add(user)
        await session.commit()
        return DEFAULT_CITY


async def get_user_city(user_id: int) -> tuple:
    """
    Возвращает кортеж (city_name, latitude, longitude, timezone) для пользователя.
    Если пользователя нет, создаёт его с городом по умолчанию и возвращает данные по умолчанию.
    """
    async with Session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return (user.city_name, user.latitude, user.longitude, user.timezone)
        return None


async def delete_user(user_id: int) -> None:
    """Удаляет запись пользователя."""
    async with Session() as session:
        stmt = select(User).where(User.user_id == user_id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            await session.delete(user)
            await session.commit()


async def update_user_prayers(user_id: int, updates: dict) -> None:
    """
    Обновляет поля времени молитв для пользователя с помощью прямого UPDATE.

    :param user_id: Telegram ID пользователя
    :param updates: словарь вида {'time_fajr': datetime/None, ...}
    """
    # Получаем список допустимых колонок модели User (исключая первичный ключ и другие системные)
    mapper = inspect(User)
    valid_columns = {c.key for c in mapper.attrs}
    # Оставляем только те ключи, которые есть в модели
    filtered_updates = {k: v for k, v in updates.items() if k in valid_columns}
    if not filtered_updates:
        logger.warning(f"No valid columns to update for user {user_id}")
        return

    async with Session() as session:
        stmt = (
            update(User)
            .where(User.user_id == user_id)
            .values(**filtered_updates)
        )
        result = await session.execute(stmt)
        await session.commit()
        if result.rowcount == 0:
            logger.warning(f"User {user_id} not found for update")
        else:
            logger.info(f"Новое время молитв сохранено в БД (прямой UPDATE)")


async def get_all_users():
    """Возвращает список всех пользователей из БД."""
    async with Session() as session:
        result = await session.execute(select(User))
        return result.scalars().all()

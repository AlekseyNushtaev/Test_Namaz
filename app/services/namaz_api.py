from datetime import datetime, timedelta
from pprint import pprint

from aiohttp import ClientSession

URL_MAIN = 'http://api.aladhan.com/v1/timings'
NAMAZ = ('Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha')


async def get_namaz(date: str, lat: float, lon: float):
    url = f'{URL_MAIN}/{date}?latitude={lat}&longitude={lon}&method=3'
    try:
        async with ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                r = await resp.json()
                return r['data']['timings']
    except Exception as e:
        print(f"Error fetching namaz times: {e}")
        return None


async def get_next(timestamp: datetime, lat: float, lon: float) -> tuple:
    # Если timestamp содержит информацию о часовом поясе, делаем его naive
    if timestamp.tzinfo is not None:
        timestamp = timestamp.replace(tzinfo=None)

    date = timestamp.strftime('%d-%m-%Y')
    timings = await get_namaz(date, lat, lon)
    for k in NAMAZ:
        t = datetime.strptime(f'{timings[k]} {date}', '%H:%M %d-%m-%Y')
        if t > timestamp:
            return k, timings[k], date
    timestamp += timedelta(days=1)
    date = timestamp.strftime('%d-%m-%Y')
    timings = await get_namaz(date, lat, lon)
    return 'Fajr', timings['Fajr'], date


if __name__ == '__main__':
    pass
    # date = datetime.now()
    # r = get_namaz(date.strftime('%d-%m-%Y'), 42.9830241, 47.5048717,)
    # r = get_next(date, 42.9830241, 47.5048717)
    # print(r)

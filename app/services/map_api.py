from geopy.adapters import AioHTTPAdapter
from geopy.geocoders import TomTom

from config import TOMTOM_API_KEY
import asyncio
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder

async def format_location(location: dict) -> dict:
    """
    :param location: raw location dictionary
    :return: formatted dictionary with the display_name, lat and lon keys
    """
    entity_types = ['municipality', 'countryTertiarySubdivision',
                    'countrySecondarySubdivision', 'countrySubdivision', 'country']
    adr = location['address']
    names = []
    for entity in entity_types:
        if ((name := adr.get(entity)) is not None) and (name not in names):
            names.append(name)
    display_name = ', '.join(names)
    return {'display_name': display_name, 'lat': location['position']['lat'], 'lon': location['position']['lon']}


async def get_loc_geocode(address: str) -> dict:
    """
    :param address: The address or query you wish to geocode.
    :return: status:
                    'Error': error during search
                    None : nothing found
                    'Multiple': multiple search results
                    'Success': multiple search results
            display_name
            lat
            lon
    """
    response = {'status': None}
    async with TomTom(TOMTOM_API_KEY, adapter_factory=AioHTTPAdapter) as locator:
        try:
            find_locations = await locator.geocode(address, exactly_one=False, typeahead=True)
        except Exception as e:
            print(e)
            find_locations = None
            response['status'] = 'Error'
    if find_locations is not None:
        locations = [loc for x in find_locations if
                     (loc := x.raw)['type'] == 'Geography' and loc['entityType'] == 'Municipality']
        count = len(locations)
        if count == 1:
            response['status'] = 'Success'
            response.update(await format_location(locations[0]))
        elif count > 1:
            response['status'] = 'Multiple'
    return response


async def get_loc_timezone(lat: float, lon: float) -> int:
    """
    :param lat: Latitude. min/max: -90 to +90
    :param lon: Longitude. min/max: -180 to +180
    :return: time zone offset in hours (integer, fractional part is truncated)
             or False if timezone cannot be determined.
    """
    tf = TimezoneFinder()
    try:
        # Поиск названия временной зоны по координатам (синхронный вызов в потоке)
        timezone_str = await asyncio.to_thread(tf.timezone_at, lng=lon, lat=lat)
    except Exception as e:
        print(f"Ошибка при поиске временной зоны: {e}")
        return False

    if timezone_str is None:
        # Например, координаты в океане
        return False

    try:
        tz = pytz.timezone(timezone_str)
        # Текущее время в этой зоне (с учётом летнего времени)
        now = datetime.now(tz)
        offset = now.utcoffset()
        if offset is None:
            return False
        # Перевод timedelta в часы (целое число, отбрасывая дробную часть)
        offset_hours = int(offset.total_seconds() / 3600)
        return offset_hours
    except Exception as e:
        print(f"Ошибка при получении смещения: {e}")
        return False

if __name__ == '__main__':
    pass

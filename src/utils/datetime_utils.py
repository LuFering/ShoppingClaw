import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.UTC  # 统一时区标准
SHANGHAI_TZ=ZoneInfo("Asia/Shanghai")
_ISO_Z_SUFFIX="+00:00"

def utc_now() -> dt.datetime:
    """返回当前 UTC 时间的 datetime 对象（带时区信息）"""
    return dt.datetime.now(UTC)

def shanghai_now() -> dt.datetime:
    return utc_now().astimezone(SHANGHAI_TZ)

def utc_now_naive() -> dt.datetime:
    """返回当前 UTC 时间的 datetime 对象（不带时区信息）"""
    return dt.datetime.now(UTC).replace(tzinfo=None)


def format_utc_datetime(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return utc_isoformat(value)


def ensure_utc(value :dt.datetime)->dt.datetime:
    """确保时间是 UTC 格式"""
    if value.tzinfo is None:
        value=value.replace(tzinfo=SHANGHAI_TZ)
    return value.astimezone(UTC)#把时间换算成 UTC 时间



def utc_isoformat(value: dt.datetime | None = None) -> str:
    """把任意时间对象转换成统一的 UTC 时间字符串"""
    value=ensure_utc(value or utc_now())
    iso_string=value.isoformat()#生成标准格式字符串
    if iso_string.endswith(_ISO_Z_SUFFIX):
        return iso_string.replace(_ISO_Z_SUFFIX,"Z")#替换时区标识符
    return iso_string

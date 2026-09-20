"""Protocol constants extracted from mbapi2020 (MIT)."""

SYSTEM_PROXY = None
REGION_EUROPE = "Europe"
REGION_NORAM = "North America"
REGION_APAC = "Asia-Pacific"
REGION_CHINA = "China"
CONF_ALLOWED_REGIONS = [REGION_EUROPE, REGION_NORAM, REGION_APAC, REGION_CHINA]
CONF_LOCALE = "locale"
CONF_COUNTRY_CODE = "country_code"
CONF_EXCLUDED_CARS = "excluded_cars"
CONF_PIN = "pin"
CONF_REGION = "region"
CONF_VIN = "vin"
CONF_TIME = "time"
CONF_DEBUG_FILE_SAVE = "save_files"
CONF_FT_DISABLE_CAPABILITY_CHECK = "cap_check_disabled"
CONF_DELETE_AUTH_FILE = "delete_auth_file"
CONF_ENABLE_CHINA_GCJ_02 = "enable_china_gcj_02"
CONF_AUTH_METHOD = "auth_method"
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_OVERWRITE_PRECONDNOW = "overwrite_cap_precondnow"
DOMAIN = "mbapi2020"
STATE_CONFIRMATION_DURATION = 60
DEFAULT_CACHE_PATH = "custom_components/mbapi2020/messages"
DEFAULT_DOWNLOAD_PATH = "custom_components/mbapi2020/resources"
DEFAULT_LOCALE = "en-GB"
DEFAULT_COUNTRY_CODE = "EN"
TOKEN_FILE_PREFIX = ".mercedesme-token-cache"
JSON_EXPORT_IGNORED_KEYS = (
    "pin",
    "access_token",
    "refresh_token",
    "username",
    "unique_id",
    "nonce",
    "_update_listeners",
    "finorvin",
    "licenseplate",
    "fin",
    "licensePlate",
    "vin",
    "dealers",
    "positionLong",
    "positionHeading",
    "id_token",
    "password",
    "title",
)
RIS_APPLICATION_VERSION_NA = "3.67.0"
RIS_APPLICATION_VERSION_CN = "1.67.0"
RIS_APPLICATION_VERSION_PA = "1.67.0"
RIS_APPLICATION_VERSION = "1.68.0 (3060)"
RIS_SDK_VERSION = "4.10.0"
RIS_SDK_VERSION_CN = "2.132.2"
RIS_OS_VERSION = "26.3"
RIS_OS_NAME = "ios"
X_APPLICATIONNAME = "mycar-store-ece"
X_APPLICATIONNAME_ECE = "mycar-store-ece"
X_APPLICATIONNAME_CN = "mycar-store-cn"
X_APPLICATIONNAME_US = "mycar-store-us"
X_APPLICATIONNAME_AP = "mycar-store-ap"
USE_PROXY = False
VERIFY_SSL = True
LOGIN_APP_ID_EU = "62778dc4-1de3-44f4-af95-115f06a3a008"
LOGIN_APP_ID_CN = "3f36efb1-f84b-4402-b5a2-68a118fec33e"
LOGIN_BASE_URI = "https://id.mercedes-benz.com"
LOGIN_BASE_URI_CN = "https://ciam-1.mercedes-benz.com.cn"
PSAG_BASE_URI = "https://psag.query.api.dvb.corpinter.net"
PSAG_BASE_URI_CN = "https://psag.query.api.dvb.corpinter.net.cn"
RCP_BASE_URI = "https://rcp-rs.query.api.dvb.corpinter.net"
RCP_BASE_URI_CN = "https://rcp-rs.query.api.dvb.corpinter.net.cn"
REST_API_BASE = "https://bff.emea-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_CN = "https://bff.cn-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_NA = "https://bff.amap-prod.mobilesdk.mercedes-benz.com"
REST_API_BASE_PA = "https://bff.amap-prod.mobilesdk.mercedes-benz.com"
WEBSOCKET_API_BASE = "wss://websocket.emea-prod.mobilesdk.mercedes-benz.com/v2/ws"
WEBSOCKET_API_BASE_NA = "wss://websocket.amap-prod.mobilesdk.mercedes-benz.com/v2/ws"
WEBSOCKET_API_BASE_PA = "wss://websocket.amap-prod.mobilesdk.mercedes-benz.com/v2/ws"
WEBSOCKET_API_BASE_CN = "wss://websocket.cn-prod.mobilesdk.mercedes-benz.com/v2/ws"
WEBSOCKET_USER_AGENT = "Mercedes-Benz/3044 CFNetwork/3860.400.22 Darwin/25.3.0"
WEBSOCKET_USER_AGENT_CN = (
    "MyStarCN/1.63.0 (com.daimler.ris.mercedesme.cn.ios; build:1758; iOS 16.3.1) Alamofire/5.4.0"
)
WEBSOCKET_USER_AGENT_PA = f"mycar-store-ap {RIS_APPLICATION_VERSION}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
WEBSOCKET_USER_AGENT_US = f"mycar-store-us v{RIS_APPLICATION_VERSION_NA}, {RIS_OS_NAME} {RIS_OS_VERSION}, SDK {RIS_SDK_VERSION}"
WIDGET_API_BASE = "https://widget.emea-prod.mobilesdk.mercedes-benz.com"
WIDGET_API_BASE_NA = "https://widget.amap-prod.mobilesdk.mercedes-benz.com"
WIDGET_API_BASE_PA = "https://widget.amap-prod.mobilesdk.mercedes-benz.com"
WIDGET_API_BASE_CN = "https://widget.cn-prod.mobilesdk.mercedes-benz.com"
DEFAULT_SOCKET_MIN_RETRY = 15
SERVICE_AUXHEAT_CONFIGURE = "auxheat_configure"
SERVICE_AUXHEAT_START = "auxheat_start"
SERVICE_AUXHEAT_STOP = "auxheat_stop"

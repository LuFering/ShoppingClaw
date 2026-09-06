# -*- coding:utf-8 -*-
class TDEStatus(object):
    def __init__(self, code, message):
        self.code = code
        self.message = message


SUCCESS = TDEStatus(0, "Success")
# Generic error codes across the whole TDE system. Range 1 to 99
INTERNAL_ERROR = TDEStatus(1, "Internal system error.")
DB_ERROR = TDEStatus(2, "Internal database error.")
INVALID_JSON = TDEStatus(3, "Invalid json input.")
# Request json is well - formed but some data field is not valid
INVALID_REQUEST_DATA = TDEStatus(4, "Invalid data in the request json.")
REQUEST_SIG_VERFIFY_ERROR = TDEStatus(5, "Validation of the request signature failed.")
# KMS specific errors.Range 100 to 199
KMS_INTERNAL_ERROR = TDEStatus(100, "KMS internal system error.")
KMS_NO_KEY_FOUND = TDEStatus(101, "No key found on KMS.")
KMS_KEY_CREATED_ALREADY = TDEStatus(102, "MK already created for this service.")
KMS_KEY_REGISTRATION_FAILED = TDEStatus(103, "Failed to register key by RKS.")
KMS_SERVICE_ALREADY_REGISTERED = TDEStatus(104, "The service is already registered")
KMS_TMS_CONNECTION_ERROR = TDEStatus(105, "Failed to connect to TMS server")
KMS_RKS_CONNECTION_ERROR = TDEStatus(106, "Failed to connect to RKS server")
KMS_KEY_ALREADY_ACTIVATED = TDEStatus(107, "Latest key already activated")
KMS_FAIL_TO_REMOVE_REDIS_CACHE = TDEStatus(108, "KMS fail to remove redis cache.")
# SDK specific errors.Range 200 to 299
SDK_INTERNAL_ERROR = TDEStatus(200, "SDK generic exception error.")
# token related
SDK_USE_INEFFECTIVE_TOKEN = TDEStatus(201, "SDK uses an ineffective token.")
SDK_USE_HARD_EXPIRED_TOKEN = TDEStatus(202, "SDK uses an expired token with hard deadline.")
SDK_USE_SOFT_EXPIRED_TOKEN = TDEStatus(203, "SDK uses an expired token with soft deadline.")
# recovery procedure related
SDK_FAIL_TO_READ_BACKUP = TDEStatus(204, "SDK cannot fetch any function keys from backup file.")
# key request / response related
SDK_RECEIVED_WRONG_KEYRESPONSE1 = TDEStatus(205, "SDK received key response with unmatched service name.")
SDK_RECEIVED_WRONG_KEYRESPONSE2 = TDEStatus(206, "SDK received key response with unmatched token id.")
SDK_CANNOT_REACH_KMS = TDEStatus(207, "SDK cannot reach KMS server.")
# Encrypt / Decrypt related
SDK_HAS_NO_AVAILABLE_ENC_KEYS = TDEStatus(208, "SDK holds a decrypt-only token or has no key to encrypt data.")
SDK_HAS_NO_CORRESPONDING_DEC_KEYS = TDEStatus(209, "SDK has no corresponding key to decrypt data.")
SDK_OPERATE_WITH_EXPIRED_KEYS = TDEStatus(210, "SDK uses old keys to encrypt/decrypt data.")
SDK_OPERATE_WITH_INACTIVE_KEYS = TDEStatus(211, "SDK uses suspended/revoked keys to encrypt/decrypt data.")
SDK_THROW_JDK_EXCEPTION = TDEStatus(212, "SDK threw generic JDK exception.")
SDK_USE_INVALID_TOKEN = TDEStatus(213, "SDK uses an invalid token.")
SDK_HAS_NO_AVAILABLE_KEYS = TDEStatus(214, "SDK has no keys in internal cache.")
SDK_HAS_CORRUPTED_KEYS = TDEStatus(215, "SDK has corrupted keys in internal cache.")
SDK_HAS_CORRUPTED_CIPHER = TDEStatus(216, "SDK tries to decrypt corrupted cipher.")
SDK_DIDNOT_SETUP_RPATH = TDEStatus(217, "SDK did not set resource path correctly.")
SDK_FAIL_TO_WRITE_KEYCACHE = TDEStatus(218, "SDK cannot write key cache file to the given resource path.")
SDK_FAIL_TO_DELETE_KEYCACHE = TDEStatus(219, "SDK fails to delete all key cache files.")
SDK_FAIL_TO_READ_KEYCACHE = TDEStatus(220, "SDK cannot fetch any function keys from cache file.")
SDK_FAIL_TO_DELETE_KEYBACKUP = TDEStatus(221, "SDK fails to delete backup file.")
# Event related
SDK_FAILS_TO_FETCH_UPDATED_KEYS = TDEStatus(227, "SDK failed to fetch rotated keys from KMS.")
SDK_TRIGGER_ROTATED_KEY_FETCH = TDEStatus(228, "SDK trigger key fetching because ciphertext is encrypted with newer keys.")
SDK_REPORT_CUR_KEYVER = TDEStatus(229, "CurKeyVer=")

# ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** TMSabout ** ** ** ** ** ** ** ** ** ** ** ** ** ** ** **
# TMS specific errors.Range 300 to 399
TMS_INTERNAL_ERROR = TDEStatus(300, "TMS internal system error.")
TMS_DB_DATA_NOTFOUND_ERROR = TDEStatus(301, "TMS-db's data not found.")
TMS_REQUEST_ARGS_ERROR = TDEStatus(302, "Request argument error.")
TMS_DB_DATA_ERROR = TDEStatus(303, "Tms db data error.")
TMS_KMS_REQUEST_EXPIRE = TDEStatus(304, " KMS request timeout.")
TMS_REQUEST_VERIFY_FAILED = TDEStatus(305, "Request signature validation failed.")
TMS_TOKEN_EXPIRE = TDEStatus(306, "The request token is expired.")
TMS_TOKEN_IS_FROZEN = TDEStatus(307, "The request token is frozen.")
TMS_TOKEN_IS_REVOKE = TDEStatus(308, "The request token is revoked.")
TMS_TOKEN_IS_NOT_IN_THE_EFFECT_TIME_RANGE = TDEStatus(309, "The token is ineffective.")
TMS_TOKEN_IN_DB_IS_NULL = TDEStatus(310, "The token in the db is null.")
TMS_NO_AVAILABLE_GRANTS_FOR_SERVICE = TDEStatus(311, "The token has no granted service.")

# RKS specific errors.Range 400 to 499
RKS_INTERNAL_ERROR = TDEStatus(400, "RKS internal system error.")
RKS_REQUEST_FORMAT_ERROR = TDEStatus(401, "Registration request format error.")
RKS_SIG_VERIFY_ERROR = TDEStatus(402, "Registration request signature validation failed.")
RKS_BACKUP_CLOSE = TDEStatus(403, "Backup service is not available.")
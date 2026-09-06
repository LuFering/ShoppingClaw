# -*- coding:utf-8 -*-
from jd.security.tde_client.http_report_client import HttpReportClient
from threading import RLock
from jd.api.base import RestApi
from jd import appinfo
from jd.security.tde import constants
from jd.security.tde.util import tde_status
from jd.security.tde.util import base64_util
from jd.security.tde.util import key_encryption
import rsa
import json
import base64
import time
import hmac
from hashlib import sha256, md5
from enum import Enum
from jd.security.tde.tde_exceptions import *
import traceback
from apscheduler.schedulers.blocking import BlockingScheduler
import threading

VERSION = "2.0.4"
KM_EPOCH = 28800
minutesBuffer=10*60*1000


class TdeClientCache(object):
    """
        A singleton Tde Client cache
        use instance method to get a Tde client
        if hits the cache and the cached client's time is available cached value will be return or create a new one
        with the init of the class, a thread witch report logs per hour
    """
    _lock = threading.Lock()
    __instance = None

    def __init__(self):
        self.__cache = dict()
        self.__lock = RLock()
        t = threading.Thread(target=self.__start_schedule)
        t.start()

    def __new__(cls, *args, **kwargs):
        if not cls.__instance:
            with cls._lock:
                if not cls.__instance:
                    cls.__instance = super().__new__(cls, *args, **kwargs)
        return cls.__instance

    def __start_schedule(self):

        scheduler = BlockingScheduler()
        scheduler.add_job(self.__flush_log, 'interval', seconds=3600, id='log_job')
        scheduler.start()

    def __flush_log(self):
        with self.__lock:
            for key in self.__cache.keys():
                self.__cache.get(key)[0].hrlc.flush()

    def instance(self, server_url, access_token, app_key, app_secret):
        """
            get a tde client via the args
        :param server_url: note the the server_url in python just mean domain name,
                hte prefix http:// or https:// will determined by RestApi.getResponse via use ssl equal to false or true
                the suffix say '/routejson' will by append automatically
        :param access_token: worth nothing to say
        :param app_key: worth nothing to say
        :param app_secret: worth nothing to say
        :return: the tde client used to encrypt or decrypt
        """
        with self.__lock:
            client_info = self.__cache.get(access_token)
            if client_info is None or time.time() - client_info[1] >= KM_EPOCH:
                if client_info is not None:
                    client_info[0].hrlc.flush()
                self.__get_instance(server_url, access_token, app_key, app_secret)
            client, _ = self.__cache.get(access_token)
            return client

    def __get_instance(self, server_url, access_token, app_key, app_secret):
        client = TdeClient(server_url, access_token, app_key, app_secret)
        if client is not None:
            self.__cache[access_token] = (client, time.time())


class TdeClient(object):
    """
    get via TdeClientCache in common, you can create your own if happy
    """
    def __init__(self, server_url, access_token, app_key, app_secret):
        self.server_url = server_url
        self.access_token = access_token
        self.app_key = app_key
        self.app_secret = app_secret
        """
        a dict used to store the token info achieve from server, the keys and value(fake value represent by server 
        side key) shown as below
       {'label': 'act', 'start_ts': 'effective', 'end_ts': 'expired',
        'id': 'id', 'key': base64.b64decode('key'),
        'service': 'service', 'stype': 'stype', 'zone': 'zone'}
        """
        self.token = {}
        self.sdk_version = int(VERSION[0])
        self.hrlc = HttpReportClient(self, server_url, access_token, app_key, app_secret)
        self.cache_ks = None
        self.major_key_ver = None
        self.key_chain_is_ready = False
        self.corrupt_key_list = set()
        self.available_key_list = dict()
        self.init_client()

    def init_client(self):
        try:
            self.request_voucher_token()
            self.cache_ks = CacheKeyStore()
            self.hrlc.insert_init_report()
            self.fetch_master_keys()
            if self.key_chain_is_ready is not True:
                raise RuntimeError(tde_status.SDK_HAS_NO_AVAILABLE_KEYS.message)
        except InvalidKeyException as ie:
            self.hrlc.insert_err_report(
                tde_status.SDK_THROW_JDK_EXCEPTION.code,
                ie.args[0],
                traceback.format_exc(),
                self.hrlc.level['error'])
            raise ie
        except InvalidTokenException as ite:
            self.hrlc.insert_err_report(
                tde_status.SDK_USE_INVALID_TOKEN.code,
                ite.args[0],
                traceback.format_exc(),
                self.hrlc.level['severe']
            )
            raise ite
        except MalformedException as me:
            self.hrlc.insert_err_report(
                tde_status.SDK_THROW_JDK_EXCEPTION.code,
                me.args[0],
                traceback.format_exc(),
                self.hrlc.level['error']
            )
            raise me
        except ServiceErrorException as se:
            raise se
        except NoValidKeyException as ne:
            raise ne
        except RuntimeError as re:
            self.hrlc.insert_err_report(
                tde_status.SDK_THROW_JDK_EXCEPTION.code,
                re.args[0],
                traceback.format_exc(),
                self.hrlc.level['error'])
            raise RuntimeError(re.args[0])
        except Exception as e:
            self.hrlc.insert_err_report(
                tde_status.SDK_INTERNAL_ERROR.code,
                e.args[0],
                traceback.format_exc(),
                self.hrlc.level['error'])
            raise RuntimeError(e.args[0])

    def encrypt_string(self, pt):
        return base64_util.encode_to_string(self.encrypt(pt))

    def encrypt(self, pt):
        self.__validate_token()
        m_key = self.cache_ks.get_enc_key_by_version(self.major_key_ver)
        self.__check_key_status_for_encryption(m_key)
        try:
            ct = m_key.encrypt(pt)
        except Exception as e:
            self.hrlc.statistic[2] += 1
            raise e
        self.hrlc.statistic[0] += 1
        return ct

    def decrypt_string(self, base64str):
        if TdeClient.is_encrypt_data(base64str):
            self.__validate_token()
            st = self.get_cipher_result(base64.b64decode(base64str))
            if st['status'] == 'UnDecryptable':
                self.hrlc.insert_err_report(
                    tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.code,
                    tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.message,
                    '', self.hrlc.level['severe']
                )
                self.hrlc.statistic[3] += 1
                raise NoValidKeyException(tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.message)
            elif st['status'] == 'Feasible':
                self.hrlc.insert_event_report(
                    tde_status.SDK_TRIGGER_ROTATED_KEY_FETCH.code,
                    tde_status.SDK_TRIGGER_ROTATED_KEY_FETCH.message
                )
                self.fetch_master_keys()
                if self.cache_ks.has_future_key_id(st['keyid']):
                    self.hrlc.insert_err_report(
                        tde_status.SDK_FAILS_TO_FETCH_UPDATED_KEYS.code,
                        tde_status.SDK_FAILS_TO_FETCH_UPDATED_KEYS.message,
                        '', self.hrlc.level['severe']
                    )
                    self.hrlc.statistic[3] += 1
                    raise NoValidKeyException(tde_status.SDK_FAILS_TO_FETCH_UPDATED_KEYS.message)
            elif st['status'] == 'Malformed':
                self.hrlc.insert_err_report(
                    tde_status.SDK_HAS_CORRUPTED_CIPHER.code,
                    tde_status.SDK_HAS_CORRUPTED_CIPHER.message,
                    '', self.hrlc.level['severe']
                )
                self.hrlc.statistic[3] += 1
                raise MalformedException(tde_status.SDK_HAS_CORRUPTED_CIPHER.message)
            m_key = self.cache_ks.search_dec_key(st['keyid'])
            self.__check_key_status_for_decryption(m_key)
            try:
                pt = m_key.decrypt(base64.b64decode(base64str))
            except Exception as e:
                self.hrlc.statistic[3] += 1
                raise e
            self.hrlc.statistic[1] += 1
            return pt

    def __check_key_status_for_decryption(self, key):
        if key is None:
            self.hrlc.insert_err_report(
                tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.code,
                tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.message,
                '', self.hrlc.level['severe']
            )
            self.hrlc.statistic[3] += 1
            raise NoValidKeyException(tde_status.SDK_HAS_NO_CORRESPONDING_DEC_KEYS.message)

    def get_cipher_result(self, ct):
        try:
            b0 = ct[0]
            flag = False
            if b0 == constants.CipherTypes.large().id or b0 == constants.CipherTypes.regular().id:
                flag = True
            mk_idx = TdeClient.__extract_key_id(ct, flag)
            if mk_idx is None:
                return {'keyid': None, 'status': 'Malformed', 'strong': False}
            if self.cache_ks.search_dec_key(mk_idx) is not None:
                return {'keyid': mk_idx, 'status': 'Decryptable', 'strong': flag}
            elif self.cache_ks.has_future_key_id(mk_idx):
                return {'keyid': mk_idx, 'status': 'Feasible', 'strong': flag}
            else:
                return {'keyid': None, 'status': 'UnDecryptable', 'strong': False}
        except RuntimeError:
            return {'keyid': None, 'status': 'Malformed', 'strong': False}

    @staticmethod
    def is_encrypt_data(val):
        try:
            if type(val) != str or base64_util.encode_to_string(base64.b64decode(val)) != val:
                return False
            val = base64.b64decode(val)
            b0 = val[0]
            flag = False
            if b0 == constants.CipherTypes.large().id or b0 == constants.CipherTypes.regular().id:
                flag = True
            mk_idx = TdeClient.__extract_key_id(val, flag)
            if mk_idx is not None and len(mk_idx) > 0:
                return True
            return False
        except Exception as e:
            dummy(e)
            return False

    @staticmethod
    def __extract_key_id(ct, strong):
        if strong:
            eid_len = int.from_bytes(ct[1:3], byteorder='big', signed=False)
            if len(ct) - 3 < eid_len:
                return None
            return ct[3: 3 + eid_len]
        else:
            if len(ct) - 2 < constants.default_keyid_len:
                return None
            return ct[2: 2 + constants.default_keyid_len]

    def __check_key_status_for_encryption(self, key):
        if key is None:
            self.hrlc.insert_err_report(
                tde_status.SDK_HAS_NO_AVAILABLE_ENC_KEYS.code, tde_status.SDK_HAS_NO_AVAILABLE_ENC_KEYS.message,
                '', self.hrlc.level['severe']
            )
            self.hrlc.statistic[2] += 1
            raise NoValidKeyException(tde_status.SDK_HAS_NO_AVAILABLE_ENC_KEYS.message)
        if key.key_status != constants.KeyStatuses.active():
            self.hrlc.insert_err_report(
                tde_status.SDK_OPERATE_WITH_INACTIVE_KEYS.code, tde_status.SDK_OPERATE_WITH_INACTIVE_KEYS.message,
                '', self.hrlc.level['error']
            )
            self.hrlc.statistic[2] += 1
            raise InvalidKeyException(tde_status.SDK_OPERATE_WITH_INACTIVE_KEYS.message)
        if key.key_usage == constants.KeyUsages.n() or key.key_usage == constants.KeyUsages.d():
            self.hrlc.statistic[2] += 1
            raise InvalidKeyPermission('Key Permission Invalid.')
        if key.expired < round(time.time() * 1000):
            self.hrlc.insert_err_report(
                tde_status.SDK_OPERATE_WITH_EXPIRED_KEYS.code, tde_status.SDK_OPERATE_WITH_EXPIRED_KEYS.message,
                '', self.hrlc.level['warn']
            )

    def __validate_token(self):
        if (self.token['start_ts'] - minutesBuffer) > round(time.time() * 1000):
            self.hrlc.insert_err_report(
                tde_status.SDK_USE_INEFFECTIVE_TOKEN.code, tde_status.SDK_USE_INEFFECTIVE_TOKEN.message,
                '', self.hrlc.level['severe']
            )
            raise InvalidTokenException(tde_status.SDK_USE_INEFFECTIVE_TOKEN.message)
        now = round(time.time() * 1000)
        if self.token['end_ts'] >= now:
            token_state = TokenState.VALID
        elif self.token['end_ts'] + constants.token_exp_delta >= now:
            token_state = TokenState.EXPIREWARNING
        else:
            token_state = TokenState.EXPIRED
        if token_state == TokenState.EXPIRED:
            self.hrlc.insert_err_report(
                tde_status.SDK_USE_HARD_EXPIRED_TOKEN.code, tde_status.SDK_USE_HARD_EXPIRED_TOKEN.message,
                '', self.hrlc.level['severe']
            )
            raise InvalidTokenException(tde_status.SDK_USE_HARD_EXPIRED_TOKEN.message)
        elif token_state == TokenState.EXPIREWARNING:
            self.hrlc.insert_err_report(
                tde_status.SDK_USE_SOFT_EXPIRED_TOKEN.code, tde_status.SDK_USE_SOFT_EXPIRED_TOKEN.message,
                '', self.hrlc.level['warn']
            )

    def request_voucher_token(self):
        request = JosVoucherInfoGetRequest(self.server_url, 80)
        request.set_app_info(appinfo(self.app_key, self.app_secret))
        customer_user_id = None
        if self.access_token is not None and self.access_token.startswith("_"):
            customer_user_id = int(self.access_token.lstrip("_"))
        if customer_user_id is None:
            json_response = request.getResponse(self.access_token)
        else:
            request.customerUserId = customer_user_id
            json_response = request.getResponse()
        voucher_info_response = json_response.get('jingdong_jos_voucher_info_get_responce')
        if '0' != voucher_info_response.get('code'):
            raise ServiceErrorException('gw platform error -> %s' % voucher_info_response.get('msg'))
        if '0' != voucher_info_response.get('response').get('errorCode'):
            raise RequestVoucherException(voucher_info_response.get('response').get('errorMsg'))
        voucher = voucher_info_response.get('response').get('data').get('voucher')
        if voucher is None:
            raise RuntimeError('Request Voucher is null')
        token_data = json.loads(base64_util.decode_to_string(voucher))
        pk = rsa.PublicKey.load_pkcs1_openssl_pem(constants.TMS_PROD_TOKEN_PUB_KEY.encode('utf-8'))
        sig = token_data.get('sig')
        data = token_data.get('data')
        external_data = token_data.get('externalData')
        zone = 'CN-0' if external_data is None else external_data.get('zone')
        verify_result = rsa.verify(json.dumps(data, separators=(',', ':')).encode('utf-8'), base64.b64decode(sig), pk)
        if verify_result != 'SHA-256':
            raise InvalidTokenException("Token Signature Validation Failed.")
        service = 'unkown host' if data.get('service') is None else data.get('service')
        self.token = {'label': data.get('act'), 'start_ts': data.get('effective'), 'end_ts': data.get('expired'),
                      'id': data.get('id'), 'key': base64.b64decode(data.get('key')),
                      'service': service, 'stype': data.get('stype'), 'zone': zone}

    def fetch_master_keys(self):
        try:
            request = JosMasterKeyGetRequest(self.server_url, 80)
            request.sdk_ver = self.sdk_version
            request.tid = self.token['id']
            request_dict = {'sdk_ver': request.sdk_ver, 'ts': request.ts, 'tid': request.tid}
            request_str = json.dumps(request_dict, separators=(',', ':'))
            request.sig = base64_util \
                .encode_to_string(hmac.new(self.token['key'], request_str
                                           .encode('utf-8'), digestmod=sha256).digest())
            request.set_app_info(appinfo(self.app_key, self.app_secret))
            json_response = request.getResponse(self.access_token)
            response = json_response.get('jingdong_jos_master_key_get_responce').get('response')
            self.corrupt_key_list.clear()
            response_code = response.get('status_code')
            if response_code == 0:
                self.__import_mkeys(response)
            else:
                if response_code in [tde_status.TMS_REQUEST_VERIFY_FAILED.code,
                                     tde_status.TMS_TOKEN_EXPIRE.code,
                                     tde_status.TMS_NO_AVAILABLE_GRANTS_FOR_SERVICE.code,
                                     tde_status.TMS_TOKEN_IS_FROZEN.code,
                                     tde_status.TMS_TOKEN_IS_REVOKE.code,
                                     tde_status.TMS_DB_DATA_NOTFOUND_ERROR.code
                                     ]:
                    self.hrlc.insert_err_report(
                        response_code, response.get('status_message'), '', self.hrlc.level['severe']
                    )
                    self.cache_ks.remove_all_m_keys()
                    self.key_chain_is_ready = False
                else:
                    self.hrlc.insert_err_report(
                        response_code, response.get('status_message'), '', self.hrlc.level['error']
                    )
                raise ServiceErrorException(response.get('status_message'))
        except Exception as e:
            dummy(e)
            self.hrlc.insert_err_report(tde_status.SDK_CANNOT_REACH_KMS.code,
                                        tde_status.SDK_CANNOT_REACH_KMS.message,
                                        traceback.format_exc(),
                                        self.hrlc.level['severe'])

    def __import_mkeys(self, response):
        if response.get('enc_service') != self.token['service']:
            self.hrlc.insert_err_report(tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE1.code,
                                        tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE1.message,
                                        '', self.hrlc.level['error'])
            raise RuntimeError(tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE1.message)
        if response.get('tid') != self.token['id']:
            self.hrlc.insert_err_report(tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE2.code,
                                        tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE2.message,
                                        '', self.hrlc.level['error'])
            raise RuntimeError(tde_status.SDK_RECEIVED_WRONG_KEYRESPONSE2.message)
        enc_rmv_list = self.cache_ks.get_key_id_list(KStoreType.ENC_STORE)
        dec_rmv_list = self.cache_ks.get_key_id_list(KStoreType.DEC_STORE)
        service_key_list = response.get('service_key_list')
        self.cache_ks.reset_future_key_ids()
        for service_key in service_key_list:
            m_keys = service_key.get('keys')
            self.available_key_list[service_key.get('service')] = len(m_keys) - 1
            # service, kid, key, k_digest, k_ver, effective_ts, exp_ls, k_type, k_usage, k_status
            for m_data in m_keys:
                m_key = Mkey(service_key.get('service'), base64.b64decode(m_data.get('id')),
                             base64.b64decode(m_data.get('key_string')), m_data.get('key_digest'),
                             m_data.get('version'), m_data.get('key_effective'), m_data.get('key_exp'),
                             m_data.get('key_type'), service_key.get('grant_usage'), m_data.get('key_status'))
                if m_key.is_valid:
                    if service_key.get('service') == self.token['service']:
                        self.major_key_ver = service_key.get('current_key_version')
                        self.cache_ks.update_key(m_data.get('id'), m_key, KStoreType.ENC_STORE)
                        if m_data.get('id') in enc_rmv_list:
                            enc_rmv_list.remove(m_data.get('id'))
                    self.cache_ks.update_key(m_data.get('id'), m_key, KStoreType.DEC_STORE)
                    if m_data.get('id') in dec_rmv_list:
                        dec_rmv_list.remove(m_data.get('id'))
                else:
                    self.corrupt_key_list.add(base64_util.encode_to_string(m_data.get('id')))
                self.cache_ks.update_future_key_ids(service_key.get('service'), service_key.get('current_key_version'))
            self.hrlc.insert_key_update_event_report(tde_status.SDK_REPORT_CUR_KEYVER.code,
                                                     tde_status.SDK_REPORT_CUR_KEYVER.message + str(self.major_key_ver),
                                                     self.major_key_ver,
                                                     self.available_key_list)
            self.available_key_list.clear()
            if len(enc_rmv_list) > 0:
                self.cache_ks.remove_keys_via_list(enc_rmv_list, KStoreType.ENC_STORE)
            if len(dec_rmv_list) > 0:
                self.cache_ks.remove_keys_via_list(dec_rmv_list, KStoreType.DEC_STORE)
            self.__send_corrupt_report()
            self.__check_valid_key_chain()

    def __send_corrupt_report(self):
        if len(self.corrupt_key_list) > 0:
            key_ids = 'keyids:' + ','.join(self.corrupt_key_list)
            self.hrlc.insert_err_report(
                tde_status.SDK_HAS_CORRUPTED_KEYS.code,
                tde_status.SDK_HAS_CORRUPTED_KEYS.message,
                key_ids,
                self.hrlc.level['error']
            )
            raise CorruptKeyException(tde_status.SDK_HAS_CORRUPTED_KEYS.message)

    def __check_valid_key_chain(self):
        self.key_chain_is_ready = False
        total_count = self.cache_ks.num_of_keys(KStoreType.ENC_STORE) + self.cache_ks.num_of_keys(KStoreType.DEC_STORE)
        if total_count == 0:
            self.hrlc.insert_err_report(
                tde_status.SDK_HAS_NO_AVAILABLE_KEYS.code,
                tde_status.SDK_HAS_NO_AVAILABLE_KEYS.message,
                '',
                self.hrlc.level['severe']
            )
            raise NoValidKeyException(tde_status.SDK_HAS_NO_AVAILABLE_KEYS.message)
        self.key_chain_is_ready = True


class JosVoucherInfoGetRequest(RestApi):
    def __init__(self, domain, port=80):
        RestApi.__init__(self, domain, port)
        self.customerUserId = None

    def getapiname(self):
        return 'jingdong.jos.voucher.info.get'


class JosMasterKeyGetRequest(RestApi):
    def __init__(self, domain, port=80):
        RestApi.__init__(self, domain, port)
        self.sig = None
        self.sdk_ver = None
        self.ts = round(time.time() * 1000)
        self.tid = None

    def getapiname(self):
        return 'jingdong.jos.master.key.get'


class KStoreType(Enum):
    ENC_STORE = 1
    DEC_STORE = 2


class TokenState(Enum):
    VALID = 1
    EXPIREWARNING = 2
    EXPIRED = 3


class CacheKeyStore(object):
    threshold_value = 3

    def __init__(self):
        self.enc_key_store = dict()
        self.dec_key_store = dict()
        self.future_key_ids = set()

    def search_dec_key(self, mk_index):
        return self.dec_key_store.get(base64_util.encode_to_string(mk_index), None)

    def num_of_keys(self, k_store_type):
        if k_store_type == KStoreType.ENC_STORE:
            return len(self.enc_key_store)
        else:
            return len(self.dec_key_store)

    def get_enc_key_by_version(self, key_ver):
        for key in self.enc_key_store.keys():
            m_key = self.enc_key_store[key]
            if key_ver == m_key.ver:
                return m_key
        return None

    def update_key(self, base64_index, m_key, k_store_type):
        if KStoreType.ENC_STORE == k_store_type:
            if base64_index not in self.enc_key_store:
                self.enc_key_store[base64_index] = m_key
            else:
                if self.enc_key_store[base64_index].key_status != m_key.key_status:
                    self.enc_key_store[base64_index] = m_key
        else:
            if base64_index not in self.dec_key_store:
                self.dec_key_store[base64_index] = m_key
            else:
                if self.dec_key_store[base64_index].key_status != m_key.key_status:
                    self.dec_key_store[base64_index] = m_key

    def remove_all_m_keys(self):
        self.enc_key_store.clear()
        self.dec_key_store.clear()

    def remove_keys_via_list(self, target_list, k_store_type):
        if k_store_type == KStoreType.ENC_STORE:
            k_store = self.enc_key_store
        else:
            k_store = self.dec_key_store
        for target in target_list:
            if target in k_store:
                del k_store[target]

    def get_key_id_list(self, k_store_type):
        if k_store_type == KStoreType.ENC_STORE:
            return list(self.enc_key_store.keys())
        else:
            return list(self.dec_key_store.keys())

    def reset_future_key_ids(self):
        self.future_key_ids.clear()

    def update_future_key_ids(self, service, max_ver):
        s_index = max_ver + 1
        for idx in range(s_index, s_index + CacheKeyStore.threshold_value):
            self.future_key_ids.add(base64_util.encode_to_string(md5((service + str(idx))
                                                                     .encode(encoding='utf-8')).digest()))

    def has_future_key_id(self, key_id):
        return base64_util.encode_to_string(key_id) in self.future_key_ids


class Mkey(object):

    def __init__(self, service, kid, key, k_digest, k_ver, effective_ts, exp_ls, k_type, k_usage, k_status):
        if service is None or kid is None:
            raise RuntimeError('ID and App fields cannot be null.')
        self.service_identifier = service
        self.id = kid
        self.ver = k_ver
        if k_ver < -1:
            raise MalformedException('Invalid key version.')
        self.key_usage = constants.KeyUsages.from_value(k_usage)
        self.key_status = constants.KeyStatuses.from_value(k_status)
        self.key_type = constants.KeyTypes.from_value(k_type)
        self.is_valid = False
        if key is not None:
            self.key = key
            self.expired = exp_ls
            self.effective = effective_ts
            self.s_key = key[0:16]
        self.key_digest = k_digest
        digest = base64_util.encode_to_string(sha256(key).digest())
        if digest == k_digest:
            self.is_valid = True

    def encrypt(self, text):
        cipher = key_encryption.aes_encrypt(self, text)
        result = constants.CipherTypes.weak().id.to_bytes(
            length=1, byteorder='big', signed=False
        ) + constants.AlgoTypes.aes_cbc_128().id.to_bytes(
            length=1, byteorder='big', signed=False
        ) + self.id + cipher
        return result

    def decrypt(self, ct):
        if ct[0] != constants.CipherTypes.weak().id:
            raise RuntimeError('Unmatch CipherText Type.')
        if ct[1] != constants.AlgoTypes.aes_cbc_128().id:
            raise RuntimeError('Unmatch Encryption Algorithm Type: %s' % ct[1])
        if ct[2: len(self.id) + 2] != self.id:
            raise RuntimeError('MalformedException("Unmatch MKey ID.')
        return key_encryption.aes_decrypt(self, ct[2 + len(self.id):])


def dummy(var):
    pass

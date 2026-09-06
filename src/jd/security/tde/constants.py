# -*- coding:utf-8 -*-
from jd.security.tde.tde_exceptions import MalformedException

default_kdf_algo = "HmacSHA256"
default_kid_algo = "MD5"
default_certdigest_algo = "SHA-256"
default_token_sign_algo = "HmacSHA256"
default_token_verify_algo = "SHA256withRSA"
default_character = "UTF-8"
default_dkey_len = 16
default_keyid_len = 16
default_cipherblk_len = 16
min_salt_len = 16
# 500 ms for default time out
http_timeout = 5000
# times for default reties
http_retry_count = 2
# default delta value for token expiration
token_exp_delta = 2592000000


TMS_PROD_TOKEN_PUB_KEY = '''
-----BEGIN PUBLIC KEY-----\n
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA3/Y3RW2mCS2+h/wdRB\n
LbjqJJI61NbWkErnWYbgZZ8woinlIyur2A6KhoCUs0SPOrJVP65Cv+6OJnPCzr5\n
gCUb1C1i1HTPRMyPuvjOnlS8Llp5t0DCCSZdcu3UKsJwDC5d0/z+lBj9YNfUew/\n
C3GhMNvPWPIv6iWlXaG2jPNtsXFuFr/kCJXZVqOmJQ6BO3X2PaV05QJEz/xszvi\n
zpws6df1QN0Ol5dQpeCr5NMBVpxojBG1RGcfchJJ8D1dVYqt0BozD6BBhGrusfb\n
KwnBIrQpZZalxzlpCFTbf/6jdrm8fdMI8hymU3tx60PyxUiFi03jaO9/IkfLRc8U\n
n2uYYrWQIDAQAB\n
-----END PUBLIC KEY-----
'''


TMS_PROD_TOKEN_CERT = '''-----BEGIN CERTIFICATE-----\n
            MIIEcDCCA1igAwIBAgIJAKCBMSvIHNiEMA0GCSqGSIb3DQEBBQUAMIGAMQswCQYD\n
            VQQGEwJDTjEQMA4GA1UECBMHQmVpamluZzEQMA4GA1UEBxMHQmVpamluZzEPMA0G\n
            A1UEChMGSkQuQ09NMQwwCgYDVQQLEwNKT1MxEzARBgNVBAMTCmpvcy5qZC5jb20x\n
            GTAXBgkqhkiG9w0BCQEWCmpvc0BqZC5jb20wIBcNMTkwMzE1MDQ1NTM2WhgPMjA1\n
            OTAzMDUwNDU1MzZaMIGAMQswCQYDVQQGEwJDTjEQMA4GA1UECBMHQmVpamluZzEQ\n
            MA4GA1UEBxMHQmVpamluZzEPMA0GA1UEChMGSkQuQ09NMQwwCgYDVQQLEwNKT1Mx\n
            EzARBgNVBAMTCmpvcy5qZC5jb20xGTAXBgkqhkiG9w0BCQEWCmpvc0BqZC5jb20w\n
            ggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDf9jdFbaYJLb6H/B1EEtuO\n
            okkjrU1taQSudZhuBlnzCiKeUjK6vYDoqGgJSzRI86slU/rkK/7o4mc8LOvmAJRv\n
            ULWLUdM9EzI+6+M6eVLwuWnm3QMIJJl1y7dQqwnAMLl3T/P6UGP1g19R7D8LcaEw\n
            289Y8i/qJaVdobaM822xcW4Wv+QIldlWo6YlDoE7dfY9pXTlAkTP/GzO+LOnCzp1\n
            /VA3Q6Xl1Cl4Kvk0wFWnGiMEbVEZx9yEknwPV1Viq3QGjMPoEGEau6x9srCcEitC\n
            lllqXHOWkIVNt//qN2ubx90wjyHKZTe3HrQ/LFSIWLTeNo738iR8tFzxSfa5hitZ\n
            AgMBAAGjgegwgeUwHQYDVR0OBBYEFHYHDa2moq7nEccftSm3x72QBWWJMIG1BgNV\n
            HSMEga0wgaqAFHYHDa2moq7nEccftSm3x72QBWWJoYGGpIGDMIGAMQswCQYDVQQG\n
            EwJDTjEQMA4GA1UECBMHQmVpamluZzEQMA4GA1UEBxMHQmVpamluZzEPMA0GA1UE\n
            ChMGSkQuQ09NMQwwCgYDVQQLEwNKT1MxEzARBgNVBAMTCmpvcy5qZC5jb20xGTAX\n
            BgkqhkiG9w0BCQEWCmpvc0BqZC5jb22CCQCggTEryBzYhDAMBgNVHRMEBTADAQH/\n
            MA0GCSqGSIb3DQEBBQUAA4IBAQAr9qLL6qkNJjtcOzYM5afdyt+KBF9iwIcKG8ca\n
            NUPNXwOFnOFw/JBKR4svjafvV3rSGs7ZtVMmASLUhrtStwfJJvXV7tdyqC0p44u/\n
            sWK6SHoTNIHX+kXbzKrkwggqeTiUlHDTw60BP/mmbrYhIwOiTNvI247iWZ4IxxyD\n
            bpFULv0gBfTVuc/ATWrHTI2pT78lIectDgUCpTOAhQIvE0PLK9nZjrsSCvW7tRED\n
            PC+6KCPYQAzxmKvRRMCHXkAVeqb/0M6GEXBIT0aYEBHKdQ7s4g1VSGrbMUL5mQsA\n
            +3fYhR+QEhE8PboH5kVct1V9tiMpx7kymJQKVfNufC3FIlyr\n
            -----END CERTIFICATE-----'''


class CipherType(object):
    def __init__(self, id_param):
        self.id = id_param


class CipherTypes(object):
    __WEAK = CipherType(0)
    __REGULAR = CipherType(1)
    __LARGE = CipherType(2)

    @staticmethod
    def weak():
        return CipherTypes.__WEAK

    @staticmethod
    def regular():
        return CipherTypes.__REGULAR

    @staticmethod
    def large():
        return CipherTypes.__LARGE

    @staticmethod
    def from_value(value):
        if value == 0:
            return CipherTypes.__WEAK
        elif value == 1:
            return CipherTypes.__REGULAR
        elif value == 2:
            return CipherTypes.__LARGE
        raise MalformedException("unknown cipher type.")


class AlgoType(object):
    def __init__(self, id_param):
        self.id = id_param


class AlgoTypes(object):
    __AES_CBC_128 = AlgoType(4)

    @staticmethod
    def aes_cbc_128():
        return AlgoTypes.__AES_CBC_128

    @staticmethod
    def from_value(value):
        if value == 4:
            return AlgoTypes.__AES_CBC_128
        else:
            return None


class KeyType(object):
    def __init__(self, id_param):
        self.id = id_param


class KeyTypes(object):
    __AES = KeyType(0)

    @staticmethod
    def aes():
        return KeyTypes.__AES

    @staticmethod
    def from_value(value):
        if value is None:
            raise MalformedException('key type is null.')
        if value == 'AES':
            return KeyTypes.__AES
        else:
            return None


class KeyUsage(object):
    def __init__(self, id_param):
        self.id = id_param


class KeyUsages(object):
    __N = KeyUsage(-1)  # none
    __E = KeyUsage(0)  # encryption only
    __D = KeyUsage(1)  # decryption only
    __ED = KeyUsage(2)  # both

    @staticmethod
    def n():
        return KeyUsages.__N

    @staticmethod
    def e():
        return KeyUsages.__E

    @staticmethod
    def d():
        return KeyUsages.__D

    @staticmethod
    def ed():
        return KeyUsages.__ED

    @staticmethod
    def from_value(value):
        if value is None:
            raise MalformedException('key usage is null.')
        if value == 'N':
            return KeyUsages.__N
        elif value == 'E':
            return KeyUsages.__E
        elif value == 'D':
            return KeyUsages.__D
        elif value == 'ED':
            return KeyUsages.__ED
        raise MalformedException("unknown key usage.")


class KeyStatus(object):
    def __init__(self, id_param):
        self.id = id_param


class KeyStatuses(object):
    __ACTIVE = KeyStatus(0)
    __SUSPENDED = KeyStatus(1)
    __REVOKED = KeyStatus(2)

    @staticmethod
    def active():
        return KeyStatuses.__ACTIVE

    @staticmethod
    def suspended():
        return KeyStatuses.__SUSPENDED

    @staticmethod
    def revoked():
        return KeyStatuses.__REVOKED

    @staticmethod
    def from_value(value):
        if value == 0:
            return KeyStatuses.__ACTIVE
        elif value == 1:
            return KeyStatuses.__SUSPENDED
        elif value == 2:
            return KeyStatuses.__REVOKED
        raise MalformedException("unknown key status.")



# -*- coding:utf-8 -*-
class SecurityException(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class MalformedException(SecurityException):
    pass


class CorruptKeyException(SecurityException):
    pass


class NoValidKeyException(SecurityException):
    pass


class ServiceErrorException(SecurityException):
    pass


class InvalidTokenException(SecurityException):
    pass


class InvalidKeyException(SecurityException):
    pass


class InvalidKeyPermission(SecurityException):
    pass


class RequestVoucherException(SecurityException):
    pass
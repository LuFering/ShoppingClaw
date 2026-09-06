# -*- coding:utf-8 -*-
import base64


def encode_to_string(param, encoding='US-ASCII'):
    return str(base64.b64encode(param), encoding)


def decode_to_string(param, encoding='US-ASCII'):
    return str(base64.b64decode(param), encoding)

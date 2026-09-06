# -*- coding:utf-8 -*-
from Crypto.Cipher import AES
import os
IV_SIZE = 16


def aes_encrypt(m_key, pt):
    """
    :param m_key: ref to class Mkey in tde_client.py
    :param pt: plain text to encrypt
    :return: encrypted value in byte form
    """
    iv = os.urandom(IV_SIZE)
    add = add_bytes_count(pt)
    data = pt + chr(IV_SIZE - len(pt.encode('utf-8')) % IV_SIZE) * add
    crypto = AES.new(m_key.s_key, AES.MODE_CBC, iv)
    encrypt_aes = crypto.encrypt(data.encode('utf-8'))
    return iv + encrypt_aes


def aes_decrypt(m_key, ct):
    """
    :param m_key: ref to class Mkey in tde_client.py
    :param ct: encrypted value in byte form
    :return: plain text
    """
    iv = ct[0:IV_SIZE]
    crypto = AES.new(m_key.s_key, AES.MODE_CBC, iv)
    decrypt_text = crypto.decrypt(ct[IV_SIZE:])
    str_text_decrypted = bytes.decode(decrypt_text, encoding='utf-8')
    return str_text_decrypted[:-ord(str_text_decrypted[-1])]


def wrap(m_key, d_key):
    """
    this wrap method will do AES.CBC directly, without padding operation,
    so if the byte length of d_key not times to 16, None will be returned
    :param m_key: ref to class Mkey in tde_client.py
    :param d_key: plain text, byte length must be times of 16
    :return: None or wrap result in byte form
    """
    if len(d_key.encode('utf-8')) % IV_SIZE != 0:
        return None
    crypto = AES.new(m_key.s_key, AES.MODE_CBC, bytes(16))
    return crypto.encrypt(d_key.encode('utf-8'))


def unwrap(m_key, ct):
    """
    did the reverse operation of wrap
    :param m_key: ref to class Mkey in tde_client.py
    :param ct: data to be unwraped in byte form
    :return:plain text
    """
    crypto = AES.new(m_key.s_key, AES.MODE_CBC, bytes(16))
    text_decrypted = crypto.decrypt(ct)
    str_text_decrypted = bytes.decode(text_decrypted, encoding='utf-8')
    return str_text_decrypted


def add_bytes_count(data):
    count = len(data.encode('utf-8'))
    if count % IV_SIZE != 0:
        add = IV_SIZE - (count % IV_SIZE)
    else:
        add = 16
    return add

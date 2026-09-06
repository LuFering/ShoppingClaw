# -*- coding:utf-8 -*-
from socket import AddressFamily
import psutil
import platform
from threading import RLock
import os
from jd.api.base import RestApi
from jd import appinfo
import random
import time
import json

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz=+-*/_|<>^~@?%&"


class HttpReportClient(object):
    def __init__(self, tde_client, server_url, access_token, app_key, app_secret):
        self.reports = dict()
        self.host_info = HttpReportClient.__get_host_info()
        self.parent = tde_client
        self.server_url = server_url
        self.access_token = access_token
        self.app_key = app_key
        self.app_secret = app_secret
        self.env_label = platform.system() + "|" + platform.version() + "|" + platform.python_version()
        self.type = {"init": 1, "exception": 2, "statistic": 3, "event": 4}
        self.level = {"info": 1, "warn": 2, "error": 3, "severe": 4}
        self.__lock = RLock()
        self.__add_cup_info()
        # statistic record present in long array
        # index: enccnt(0) deccnt(1) encerrcnt(2) decerrcnt(3)
        self.statistic = [0, 0, 0, 0]

    @staticmethod
    def __get_host_info():
        for name, info in psutil.net_if_addrs().items():
            for ip_address in info:
                if AddressFamily.AF_INET == ip_address.family:
                    return ip_address.address
        return "Unknown host"

    def __add_cup_info(self):
        lower_env_label = self.env_label.lower()
        cpu_info = 'Unknown'
        if lower_env_label.find('linux') != -1:
            cpu_info = os.popen('cat /proc/cpuinfo | grep "model name" | uniq').read().split(':')[1].rstrip(
                '\n').strip()
        elif lower_env_label.find('mac') != -1:
            cpu_info = os.popen('sysctl -n machdep.cpu.brand_string').read().rstrip('\n').strip()
        elif lower_env_label.find('windows') != -1:
            cmd_result = os.popen('wmic cpu get name')
            cpu_info = cmd_result.read().replace('Name', '').replace('\n', '', -1).strip()
            cmd_result.read()
        self.env_label = self.env_label + '|' + cpu_info

    def flush(self):
        self.insert_statistic_report()
        self.send_all_reports()

    def send_all_reports(self):
        with self.__lock:
            for key in self.reports.keys():
                val = self.reports[key]
                request = JosSecretApiReportRequest(self.server_url, 80)
                request.businessId = val['businessId']
                request.text = val['text']
                request.attribute = json.dumps(val['attributes'])
                request.set_app_info(appinfo(self.app_key, self.app_secret))
                res = request.getResponse(self.access_token)
                if res is not None and res.get('serviceCode') == 0:
                    del self.reports[key]

    def insert_init_report(self):
        with self.__lock:
            init_msg = {
                'businessId': ''.join(random.sample(ALPHABET, 40)),
                'text': 'INIT',
                'attributes': {
                    'type': self.type['init'],
                    'host': self.host_info,
                    'level': self.level['info'],
                    'service': self.parent.token['service'],
                    'sdk_ver': self.parent.sdk_version,
                    'env': self.env_label,
                    'ts': round(time.time() * 1000)
                }
            }
            self.reports[self.type['init']] = init_msg

    def insert_statistic_report(self):
        with self.__lock:
            statistic_msg = {
                'businessId': ''.join(random.sample(ALPHABET, 40)),
                'text': 'STATISTIC',
                'attributes': {
                    'enccnt':  str(self.statistic[0]),
                    'deccnt': str(self.statistic[1]),
                    'encerrcnt': str(self.statistic[2]),
                    'decerrcnt': str(self.statistic[3]),
                    'type': self.type['statistic'],
                    'host': self.host_info,
                    'level': self.level['info'],
                    'service': self.parent.token['service'],
                    'sdk_ver': self.parent.sdk_version,
                    'env': self.env_label,
                    'ts': round(time.time() * 1000)
                }
            }
            self.reports[self.type['statistic']] = statistic_msg
            self.statistic = [0, 0, 0, 0]

    def insert_event_report(self, event_code, event_detail):
        with self.__lock:
            event_msg = {
                'businessId': ''.join(random.sample(ALPHABET, 40)),
                'text': 'EVENT',
                'attributes': {
                    'code': event_code,
                    'event': event_detail,
                    'type': self.type['event'],
                    'host': self.host_info,
                    'level': self.level['info'],
                    'service': self.parent.token['service'],
                    'sdk_ver': self.parent.sdk_version,
                    'env': self.env_label,
                    'ts': round(time.time() * 1000)
                }
            }
            request = JosSecretApiReportRequest(self.server_url, 80)
            request.businessId = event_msg['businessId']
            request.text = event_msg['text']
            request.set_app_info(appinfo(self.app_key, self.app_secret))
            request.getResponse(self.access_token)

    def insert_key_update_event_report(self, event_code, event_detail, major_key_ver, key_list):
        with self.__lock:
            key_update_event_msg = {
                'businessId': ''.join(random.sample(ALPHABET, 40)),
                'text': 'EVENT',
                'attributes': {
                    'cur_key': major_key_ver,
                    'keylist': key_list,
                    'type': self.type['event'],
                    'host': self.host_info,
                    'level': self.level['info'],
                    'service': self.parent.token['service'],
                    'sdk_ver': self.parent.sdk_version,
                    'env': self.env_label,
                    'ts': round(time.time() * 1000)
                }
            }
            request = JosSecretApiReportRequest(self.server_url, 80)
            request.businessId = key_update_event_msg['businessId']
            request.text = key_update_event_msg['text']
            request.attribute = json.dumps(key_update_event_msg['attributes'])
            request.set_app_info(appinfo(self.app_key, self.app_secret))
            request.getResponse(self.access_token)

    def insert_err_report(self, code, detail, stack_trace, level):
        with self.__lock:
            err_msg = {
                'businessId': ''.join(random.sample(ALPHABET, 40)),
                'text': 'EXCEPTION',
                'attributes': {
                    'type': self.type['exception'],
                    'host': self.host_info,
                    'level': level,
                    'service': self.parent.token['service'],
                    'sdk_ver': self.parent.sdk_version,
                    'env': self.env_label,
                    'ts': round(time.time() * 1000),
                    'code': code,
                    'msg': detail,
                    'heap': stack_trace
                }
            }
            if level == self.level['error'] or level == self.level['severe']:
                request = JosSecretApiReportRequest(self.server_url, 80)
                request.businessId = err_msg['businessId']
                request.text = err_msg['text']
                request.attribute = json.dumps(err_msg['attributes'])
                request.set_app_info(appinfo(self.app_key, self.app_secret))
                request.getResponse(self.access_token)
            else:
                self.reports[code] = err_msg


class JosSecretApiReportRequest(RestApi):
    def __init__(self, domain, port=80):
        RestApi.__init__(self, domain, port)
        self.serverUrl = None
        self.businessId = None
        self.text = None
        self.attribute = None

    def process_with_url_before_request(self, url):
        self.serverUrl = url

    def getapiname(self):
        return 'jingdong.jos.secret.api.report.get'

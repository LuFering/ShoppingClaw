from jd.api.base import RestApi

class KplOpenWfpVscVerifiedNotifyRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.vsc.verifiedNotify'

		def get_version(self):
			return '1.0'
			
	

class VerifyRecord(object):
		def __init__(self):
			"""
			"""
			self.certId = None
			self.verifyingTimes = None
			self.mobile = None
			self.operator = None


class Data(object):
		def __init__(self):
			"""
			"""
			self.recordList = None
			self.transactionId = None


class MerchantRequestWrap(object):
		def __init__(self):
			"""
			"""
			self.merchantCode = None
			self.data = None






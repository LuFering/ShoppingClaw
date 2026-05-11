from jd.api.base import RestApi

class KplOpenWfpVscVerifyRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.vsc.verify'

		def get_version(self):
			return '1.0'
			
	

class VerifyingCert(object):
		def __init__(self):
			"""
			"""
			self.cardNum = None
			self.pwd = None
			self.verifyingTimes = None
			self.mobile = None


class Data(object):
		def __init__(self):
			"""
			"""
			self.transactionId = None
			self.verifyingCertList = None
			self.keepReserve = None
			self.erpOrderId = None


class RequestWrap(object):
		def __init__(self):
			"""
			"""
			self.merchantCode = None
			self.appCode = None
			self.token = None
			self.businessType = None
			self.data = None
			self.operatorPerson = None
			self.clientIp = None
			self.clientPort = None
			self.trackerId = None






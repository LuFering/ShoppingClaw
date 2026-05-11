from jd.api.base import RestApi

class KplOpenWfpVscMakeCertCallbackRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.vsc.makeCertCallback'

		def get_version(self):
			return '1.0'
			
	

class Cert(object):
		def __init__(self):
			"""
			"""
			self.certId = None
			self.cardNum = None
			self.pwd = None
			self.effectiveTime = None
			self.expiryTime = None
			self.leftTimes = None


class Data(object):
		def __init__(self):
			"""
			"""
			self.certList = None
			self.status = None
			self.orderId = None
			self.errMsg = None


class MerchantRequestWrap(object):
		def __init__(self):
			"""
			"""
			self.merchantCode = None
			self.data = None






from jd.api.base import RestApi

class KplOpenWfpVscPreviewRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.vsc.preview'

		def get_version(self):
			return '1.0'
			
	

class Data(object):
		def __init__(self):
			"""
			"""
			self.cardNum = None
			self.pwd = None


class RequestWrap(object):
		def __init__(self):
			"""
			"""
			self.appCode = None
			self.businessType = None
			self.merchantCode = None
			self.token = None
			self.clientIp = None
			self.clientPort = None
			self.trackerId = None
			self.source = None
			self.operatorPerson = None
			self.data = None






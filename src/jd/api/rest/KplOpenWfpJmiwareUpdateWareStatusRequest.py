from jd.api.base import RestApi

class KplOpenWfpJmiwareUpdateWareStatusRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.jmiware.updateWareStatus'

		def get_version(self):
			return '1.0'
			
	

class Param(object):
		def __init__(self):
			"""
			"""
			self.venderId = None
			self.wareId = None
			self.opType = None
			self.opeReason = None
			self.opName = None
			self.opIp = None
			self.sourceId = None
			self.uuid = None
			self.port = None






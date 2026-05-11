from jd.api.base import RestApi

class UnionOpenCpActivityCancelValidateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpVerifyCancelActivityReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.cancel.validate'

		def get_version(self):
			return '1.0'
			
	

class CpVerifyCancelActivityReq(object):
		def __init__(self):
			"""
			"""
			self.idList = None
			self.examineStatus = None
			self.examineRejectReason = None






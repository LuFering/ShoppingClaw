from jd.api.base import RestApi

class UnionOpenUserPidGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.pidReq = None

		def getapiname(self):
			return 'jd.union.open.user.pid.get'

		def get_version(self):
			return '1.0'
			
	

class PidReq(object):
		def __init__(self):
			"""
			"""
			self.unionId = None
			self.childUnionId = None
			self.promotionType = None
			self.positionName = None
			self.mediaName = None






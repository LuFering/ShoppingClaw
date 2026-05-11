from jd.api.base import RestApi

class UnionOpenStatisticsCpActivityQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityEffectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.cp.activity.query'

		def get_version(self):
			return '1.0'
			
	

class CpActivityEffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None






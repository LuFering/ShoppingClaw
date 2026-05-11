from jd.api.base import RestApi

class UnionOpenStatisticsRedpacketAgentQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.effectDataAgentReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.redpacket.agent.query'

		def get_version(self):
			return '1.0'
			
	

class EffectDataAgentReq(object):
		def __init__(self):
			"""
			"""
			self.actId = None
			self.startDate = None
			self.endDate = None
			self.pageIndex = None
			self.pageSize = None
			self.type = None






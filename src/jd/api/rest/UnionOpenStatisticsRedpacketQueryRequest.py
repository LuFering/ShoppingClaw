from jd.api.base import RestApi

class UnionOpenStatisticsRedpacketQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.effectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.redpacket.query'

		def get_version(self):
			return '1.0'
			
	

class EffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.actId = None
			self.positionId = None
			self.startDate = None
			self.endDate = None
			self.pageIndex = None
			self.pageSize = None
			self.key = None
			self.type = None
			self.channelIds = None






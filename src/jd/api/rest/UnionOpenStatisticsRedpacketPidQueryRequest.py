from jd.api.base import RestApi

class UnionOpenStatisticsRedpacketPidQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.redPacketPidEffectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.redpacket.pid.query'

		def get_version(self):
			return '1.0'
			
	

class RedPacketPidEffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.actId = None
			self.pid = None
			self.startDate = None
			self.endDate = None
			self.pageIndex = None
			self.pageSize = None






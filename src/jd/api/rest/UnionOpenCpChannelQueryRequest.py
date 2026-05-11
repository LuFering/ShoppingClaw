from jd.api.base import RestApi

class UnionOpenCpChannelQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpChannelQueryReq = None

		def getapiname(self):
			return 'jd.union.open.cp.channel.query'

		def get_version(self):
			return '1.0'
			
	

class CpChannelQueryReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.endDate = None
			self.pageSize = None
			self.idList = None
			self.startDate = None






from jd.api.base import RestApi

class UnionOpenChannelRelationQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.channelRelationQueryReq = None

		def getapiname(self):
			return 'jd.union.open.channel.relation.query'

		def get_version(self):
			return '1.0'
			
	

class ChannelRelationQueryReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.channelId = None
			self.startIndex = None






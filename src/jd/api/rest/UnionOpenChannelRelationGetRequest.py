from jd.api.base import RestApi

class UnionOpenChannelRelationGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.channelRelationGetReq = None

		def getapiname(self):
			return 'jd.union.open.channel.relation.get'

		def get_version(self):
			return '1.0'
			
	

class ChannelRelationGetReq(object):
		def __init__(self):
			"""
			"""
			self.inviteCode = None
			self.note = None
			self.channelNote = None






from jd.api.base import RestApi

class UnionOpenChannelInvitecodeGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.channelInviteReq = None

		def getapiname(self):
			return 'jd.union.open.channel.invitecode.get'

		def get_version(self):
			return '1.0'
			
	

class ChannelInviteReq(object):
		def __init__(self):
			"""
			"""
			self.inviteType = None
			self.channelType = None






from jd.api.base import RestApi

class UnionOpenCpChannelDefaultGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpDefaultChannelGetReq = None

		def getapiname(self):
			return 'jd.union.open.cp.channel.default.get'

		def get_version(self):
			return '1.0'
			
	

class CpDefaultChannelGetReq(object):
		def __init__(self):
			"""
			"""
			self.id = None






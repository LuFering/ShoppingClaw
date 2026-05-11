from jd.api.base import RestApi

class UnionOpenCpChannelDeleteRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpChannelDeleteReq = None

		def getapiname(self):
			return 'jd.union.open.cp.channel.delete'

		def get_version(self):
			return '1.0'
			
	

class CpChannelDeleteReq(object):
		def __init__(self):
			"""
			"""
			self.id = None






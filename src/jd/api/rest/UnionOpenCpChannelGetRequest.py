from jd.api.base import RestApi

class UnionOpenCpChannelGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpChannelGetReq = None

		def getapiname(self):
			return 'jd.union.open.cp.channel.get'

		def get_version(self):
			return '1.0'
			
	

class CpChannelGetReq(object):
		def __init__(self):
			"""
			"""
			self.name = None






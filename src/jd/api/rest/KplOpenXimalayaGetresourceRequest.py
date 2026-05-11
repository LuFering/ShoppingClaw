from jd.api.base import RestApi

class KplOpenXimalayaGetresourceRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.wrap = None

		def getapiname(self):
			return 'jd.kpl.open.ximalaya.getresource'

		def get_version(self):
			return '1.0'
			
	

class Wrap(object):
		def __init__(self):
			"""
			"""
			self.requestURI = None
			self.requestMethod = None
			self.requestQueryString = None
			self.requestParameterMap = None
			self.timestamp = None






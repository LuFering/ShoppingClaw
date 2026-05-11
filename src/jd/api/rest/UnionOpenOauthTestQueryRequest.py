from jd.api.base import RestApi

class UnionOpenOauthTestQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.oauthTestReq = None

		def getapiname(self):
			return 'jd.union.open.oauth.test.query'

		def get_version(self):
			return '1.0'
			
	

class OauthTestReq(object):
		def __init__(self):
			"""
			"""
			self.unionId = None
			self.key = None
			self.unionType = None
			self.pageIndex = None
			self.pageSize = None
			self.jcommand = None






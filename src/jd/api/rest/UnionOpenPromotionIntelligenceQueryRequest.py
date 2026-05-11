from jd.api.base import RestApi

class UnionOpenPromotionIntelligenceQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.req = None

		def getapiname(self):
			return 'jd.union.open.promotion.intelligence.query'

		def get_version(self):
			return '1.0'
			
	

class Req(object):
		def __init__(self):
			"""
			"""
			self.title = None
			self.type = None
			self.cid1List = None
			self.status = None
			self.essence = None
			self.pageIndex = None
			self.pageSize = None
			self.pid = None
			self.subUnionId = None
			self.siteId = None
			self.positionId = None
			self.ext1 = None






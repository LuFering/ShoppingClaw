from jd.api.base import RestApi

class UnionOpenGoodsCombinationQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.combination.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReq(object):
		def __init__(self):
			"""
			"""
			self.batchId = None
			self.needClickUrl = None
			self.positionId = None
			self.pid = None
			self.subUnionId = None
			self.channelId = None
			self.ext = None
			self.pageIndex = None
			self.pageSize = None






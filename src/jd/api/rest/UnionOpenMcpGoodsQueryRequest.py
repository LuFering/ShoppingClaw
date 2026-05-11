from jd.api.base import RestApi

class UnionOpenMcpGoodsQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReqDTO = None

		def getapiname(self):
			return 'jd.union.open.mcp.goods.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReqDTO(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.keyword = None
			self.userIdType = None
			self.userId = None
			self.fields = None
			self.channelId = None
			self.cid = None
			self.shopTypes = None
			self.sort = None
			self.sortName = None
			self.exactMatch = None
			self.pricefrom = None
			self.priceto = None
			self.openId = None






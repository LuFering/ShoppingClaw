from jd.api.base import RestApi

class UnionOpenGoodsSeckillQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.goodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.seckill.query'

		def get_version(self):
			return '1.0'
			
	

class GoodsReq(object):
		def __init__(self):
			"""
			"""
			self.skuIds = None
			self.pageIndex = None
			self.pageSize = None
			self.isBeginSecKill = None
			self.secKillPriceFrom = None
			self.secKillPriceTo = None
			self.cid1 = None
			self.cid2 = None
			self.cid3 = None
			self.owner = None
			self.commissionShareFrom = None
			self.commissionShareTo = None
			self.sortName = None
			self.sort = None






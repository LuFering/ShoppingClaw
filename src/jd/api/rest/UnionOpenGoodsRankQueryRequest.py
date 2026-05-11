from jd.api.base import RestApi

class UnionOpenGoodsRankQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.RankGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.goods.rank.query'

		def get_version(self):
			return '1.0'
			
	

class RankGoodsReq(object):
		def __init__(self):
			"""
			"""
			self.rankId = None
			self.sortType = None
			self.pageIndex = None
			self.pageSize = None






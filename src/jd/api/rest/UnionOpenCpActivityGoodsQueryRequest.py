from jd.api.base import RestApi

class UnionOpenCpActivityGoodsQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityGoodsReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.goods.query'

		def get_version(self):
			return '1.0'
			
	

class CpActivityGoodsReq(object):
		def __init__(self):
			"""
			"""
			self.activityId = None
			self.pageIndex = None
			self.pageSize = None
			self.type = None
			self.skuId = None
			self.status = None
			self.itemId = None
			self.fields = None






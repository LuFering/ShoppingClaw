from jd.api.base import RestApi

class UnionOpenCpActivityGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityGetReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.get'

		def get_version(self):
			return '1.0'
			
	

class CpActivityGetReq(object):
		def __init__(self):
			"""
			"""
			self.serviceRateMin = None
			self.priceMax = None
			self.weeklySales = None
			self.title = None
			self.type = None
			self.dongdong = None
			self.priceMin = None
			self.jdGoodShop = None
			self.batchCommissionRateMin = None
			self.activityId = None
			self.evaluationCnt = None
			self.shipping = None
			self.jdLogistics = None
			self.startTime = None
			self.freightInsurance = None
			self.qq = None
			self.coupon = None
			self.estimateSales = None
			self.purchase = None
			self.favorableRate = None
			self.goodsType = None
			self.endTime = None
			self.popServiceRateMin = None
			self.status = None






from jd.api.base import RestApi

class AfterSaleAvailableNumberCompQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.param = None

		def getapiname(self):
			return 'biz.afterSale.availableNumberComp.query'

		def get_version(self):
			return '1.0'
			
	

class Param(object):
		def __init__(self):
			"""
			"""
			self.jdOrderId = None
			self.skuId = None






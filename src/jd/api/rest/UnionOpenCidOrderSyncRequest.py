from jd.api.base import RestApi

class UnionOpenCidOrderSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.syncCidOrderReq = None

		def getapiname(self):
			return 'jd.union.open.cid.order.sync'

		def get_version(self):
			return '1.0'
			
	

class SyncCidOrderReq(object):
		def __init__(self):
			"""
			"""
			self.sceneType = None
			self.eventType = None
			self.eventTime = None
			self.requestId = None
			self.orderId = None
			self.id = None
			self.cosPrice = None
			self.skuId = None
			self.skuName = None
			self.shopId = None
			self.orderPlatform = None






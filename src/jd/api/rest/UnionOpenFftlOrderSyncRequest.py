from jd.api.base import RestApi

class UnionOpenFftlOrderSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.syncShOrderReq = None

		def getapiname(self):
			return 'jd.union.open.fftl.order.sync'

		def get_version(self):
			return '1.0'
			
	

class SyncShOrderReq(object):
		def __init__(self):
			"""
			"""
			self.bizType = None
			self.sceneType = None
			self.requestId = None
			self.accountId = None
			self.eventType = None
			self.eventTime = None
			self.jdEventType = None
			self.jdEventTime = None
			self.orderId = None
			self.callback = None
			self.payAmount = None
			self.skuId = None
			self.shopId = None
			self.orderPlatform = None
			self.extInfo = None






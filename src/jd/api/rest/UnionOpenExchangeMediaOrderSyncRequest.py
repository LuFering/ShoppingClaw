from jd.api.base import RestApi

class UnionOpenExchangeMediaOrderSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.orderReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.order.sync'

		def get_version(self):
			return '1.0'
			
	

class MediaOrderContent(object):
		def __init__(self):
			"""
			"""
			self.authorPrice = None
			self.authorName = None
			self.authorFansNum = None
			self.pubTime = None
			self.contentId = None
			self.authorId = None
			self.authorReferencePrice = None
			self.pubLink = None
			self.contentName = None
			self.oldContentId = None
			self.listingPrice = None
			self.serviceFee = None
			self.balancePrice = None
			self.orderTotalPrice = None


class MediaOrder(object):
		def __init__(self):
			"""
			"""
			self.orderType = None
			self.orderContentList = None
			self.orderId = None
			self.orderStatus = None
			self.orderPrice = None
			self.cancelReason = None
			self.taskId = None
			self.balancePrice = None
			self.orderName = None
			self.balanceStatus = None
			self.orderTime = None
			self.compensatePrice = None


class OrderReq(object):
		def __init__(self):
			"""
			"""
			self.mediaOrder = None
			self.uuid = None






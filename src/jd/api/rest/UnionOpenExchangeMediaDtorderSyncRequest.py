from jd.api.base import RestApi

class UnionOpenExchangeMediaDtorderSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.syncDtOrderReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.dtorder.sync'

		def get_version(self):
			return '1.0'
			
	

class MediaDtOrder(object):
		def __init__(self):
			"""
			"""
			self.bvId = None
			self.promotionPurposeType = None
			self.creativeName = None
			self.unitName = None
			self.campaignId = None
			self.authorFansNum = None
			self.authorId = None
			self.creativeId = None
			self.accountId = None
			self.authorName = None
			self.unitId = None
			self.campaignName = None
			self.taskId = None
			self.promotionPurposeText = None


class SyncDtOrderReq(object):
		def __init__(self):
			"""
			"""
			self.mediaDtOrder = None
			self.uuid = None






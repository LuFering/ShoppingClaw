from jd.api.base import RestApi

class UnionOpenExchangeMediaEffectDataSyncRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.effectDataReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.effect.data.sync'

		def get_version(self):
			return '1.0'
			
	

class MediaEffectData(object):
		def __init__(self):
			"""
			"""
			self.commentNum = None
			self.orderId = None
			self.activeUvNum = None
			self.authorFansNum = None
			self.contentId = None
			self.followUvNum = None
			self.playUvNum = None
			self.viewDate = None
			self.cycle = None
			self.shareNum = None
			self.taskId = None
			self.likeNum = None
			self.playNum = None
			self.brandId = None
			self.categoryId = None
			self.convertUvNum = None


class EffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.mediaEffectDataList = None
			self.uuid = None






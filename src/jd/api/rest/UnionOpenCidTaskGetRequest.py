from jd.api.base import RestApi

class UnionOpenCidTaskGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cidTaskReq = None

		def getapiname(self):
			return 'jd.union.open.cid.task.get'

		def get_version(self):
			return '1.0'
			
	

class CidTaskReq(object):
		def __init__(self):
			"""
			"""
			self.uuid = None
			self.adownerPin = None
			self.taskId = None
			self.taskName = None
			self.taskDescription = None
			self.materialId = None
			self.appLandingUrl = None
			self.sceneType = None
			self.traceScope = None
			self.traceEventType = None
			self.tracePoint = None
			self.tracePeriod = None
			self.traceSpuBlacklist = None
			self.traceSkuBlacklist = None
			self.traceSpuWhitelist = None
			self.traceSkuWhitelist = None
			self.traceRepeat = None
			self.siteId = None
			self.positionId = None
			self.secondTrace = None
			self.transmitBackDeduction = None
			self.orderFilterThreshold = None
			self.transmitDelay = None
			self.traceFrequencyControl = None
			self.landingPageType = None
			self.skuId = None






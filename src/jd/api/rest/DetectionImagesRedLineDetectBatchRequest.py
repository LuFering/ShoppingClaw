from jd.api.base import RestApi

class DetectionImagesRedLineDetectBatchRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.timeZone = None
			self.key = None
			self.value = None
			self.detectItem = None
			self.imageUrl = None

		def getapiname(self):
			return 'jingdong.detection.imagesRedLineDetectBatch'

			






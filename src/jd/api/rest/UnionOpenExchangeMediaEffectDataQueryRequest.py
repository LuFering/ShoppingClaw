from jd.api.base import RestApi

class UnionOpenExchangeMediaEffectDataQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.effectDataQueryReq = None

		def getapiname(self):
			return 'jd.union.open.exchange.media.effect.data.query'

		def get_version(self):
			return '1.0'
			
	

class EffectDataQueryReq(object):
		def __init__(self):
			"""
			"""
			self.maxId = None
			self.pageSize = None
			self.uuid = None
			self.actDate = None
			self.taskIdList = None
			self.businessType = None






from jd.api.base import RestApi

class UnionOpenStatisticsSecretQueryRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.secretEffectDataReq = None

		def getapiname(self):
			return 'jd.union.open.statistics.secret.query'

		def get_version(self):
			return '1.0'
			
	

class SecretEffectDataReq(object):
		def __init__(self):
			"""
			"""
			self.pageIndex = None
			self.pageSize = None
			self.secretId = None
			self.startDate = None
			self.endDate = None
			self.secretThemeId = None
			self.secretKeyWord = None
			self.applyStartTime = None
			self.applyEndTime = None
			self.channelId = None






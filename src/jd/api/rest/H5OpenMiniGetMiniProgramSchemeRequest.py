from jd.api.base import RestApi

class H5OpenMiniGetMiniProgramSchemeRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.path = None
			self.query = None
			self.envVersion = None
			self.venderId = None
			self.userId = None

		def getapiname(self):
			return 'jingdong.h5OpenMini.getMiniProgramScheme'

			






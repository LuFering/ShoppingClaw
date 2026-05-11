from jd.api.base import RestApi

class UnionOpenCpActivityGoodsValidateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.cpActivityGoodsVerifyReq = None

		def getapiname(self):
			return 'jd.union.open.cp.activity.goods.validate'

		def get_version(self):
			return '1.0'
			
	

class CpActivityGoodsVerifyReq(object):
		def __init__(self):
			"""
			"""
			self.goodsVerifyInfo = None
			self.activityId = None
			self.examineStatus = None






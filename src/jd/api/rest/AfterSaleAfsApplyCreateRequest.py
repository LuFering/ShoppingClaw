from jd.api.base import RestApi

class AfterSaleAfsApplyCreateRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.param = None

		def getapiname(self):
			return 'biz.afterSale.afsApply.create'

		def get_version(self):
			return '1.0'
			
	

class AsCustomerDto(object):
		def __init__(self):
			"""
			"""
			self.customerContactName = None
			self.customerTel = None
			self.customerMobilePhone = None
			self.customerEmail = None
			self.customerPostcode = None


class AsPickwareDto(object):
		def __init__(self):
			"""
			"""
			self.pickwareType = None
			self.pickwareProvince = None
			self.pickwareCity = None
			self.pickwareCounty = None
			self.pickwareVillage = None
			self.pickwareAddress = None


class AsReturnwareDto(object):
		def __init__(self):
			"""
			"""
			self.returnwareType = None
			self.returnwareProvince = None
			self.returnwareCity = None
			self.returnwareCounty = None
			self.returnwareVillage = None
			self.returnwareAddress = None


class AsDetailDto(object):
		def __init__(self):
			"""
			"""
			self.skuId = None
			self.skuNum = None


class Param(object):
		def __init__(self):
			"""
			"""
			self.jdOrderId = None
			self.customerExpect = None
			self.questionDesc = None
			self.isNeedDetectionReport = None
			self.questionPic = None
			self.asCustomerDto = None
			self.asPickwareDto = None
			self.asReturnwareDto = None
			self.asDetailDto = None
			self.isHasPackage = None
			self.packageDesc = None






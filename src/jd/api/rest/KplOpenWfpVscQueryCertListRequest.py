from jd.api.base import RestApi

class KplOpenWfpVscQueryCertListRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jingdong.kpl.open.wfp.vsc.queryCertList'

			
	

class QueryData(object):
		def __init__(self):
			"""
			"""
			self.merchantCardId = None
			self.queryMerchantCode = None
			self.queryBusinessType = None
			self.queryCardNum = None
			self.cardNumList = None
			self.erpOrderId = None
			self.skuId = None
			self.providedTime = None
			self.effectiveTime = None
			self.lastVerifiedTime = None
			self.expiredTime = None
			self.modified = None
			self.providedTimeMax = None
			self.effectiveTimeMax = None
			self.lastVerifiedTimeMax = None
			self.expiredTimeMax = None
			self.modifiedMax = None
			self.batchNum = None


class Data(object):
		def __init__(self):
			"""
			"""
			self.pageNum = None
			self.pageSize = None
			self.queryData = None


class QueryCertListRequestWrap(object):
		def __init__(self):
			"""
			"""
			self.appCode = None
			self.businessType = None
			self.merchantCode = None
			self.token = None
			self.clientIp = None
			self.clientPort = None
			self.source = None
			self.operatorPerson = None
			self.data = None






from jd.api.base import RestApi

class KplOpenWfpJmiwareAddWareRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.interfaceName = None
			self.methodName = None
			self.param = None

		def getapiname(self):
			return 'jd.kpl.open.wfp.jmiware.addWare'

		def get_version(self):
			return '1.0'
			
	

class JmiWareImageParam(object):
		def __init__(self):
			"""
			"""
			self.wareId = None
			self.imgPath = None
			self.zone = None
			self.indexId = None


class AttrValue(object):
		def __init__(self):
			"""
			"""
			self.valueObj = None
			self.aliasName = None


class AttrParam(object):
		def __init__(self):
			"""
			"""
			self.letter = None
			self.attrValue = None


class JmiSkuPriceParam(object):
		def __init__(self):
			"""
			"""
			self.jSkuId = None
			self.dateDay = None
			self.stock = None
			self.price = None
			self.settingList = None
			self.extPropertyList = None
			self.preStock = None


class JmiWareSkuParam(object):
		def __init__(self):
			"""
			"""
			self.jSkuId = None
			self.jWareId = None
			self.outerId = None
			self.skuPrice = None
			self.quantity = None
			self.indexOuterId = None
			self.saleList = None
			self.extSetting = None
			self.preStock = None
			self.mainVideoId = None
			self.infoVideoId = None
			self.mainVideoUrl = None
			self.infoVideoUrl = None
			self.jmiSkuPrices = None


class JmiWareParam(object):
		def __init__(self):
			"""
			"""
			self.opName = None
			self.opIp = None
			self.sourceId = None
			self.uuid = None
			self.port = None
			self.jWareId = None
			self.catId = None
			self.venderId = None
			self.shopId = None
			self.title = None
			self.subTitle = None
			self.marketPrice = None
			self.price = None
			self.outerId = None
			self.quantity = None
			self.logo = None
			self.operateType = None
			self.note = None
			self.wareImages = None
			self.features = None
			self.url = None
			self.urlWord = None
			self.onlineTime = None
			self.offlineTime = None
			self.appNote = None
			self.shopCategory = None
			self.wareSettingList = None
			self.categorySettingList = None
			self.skus = None






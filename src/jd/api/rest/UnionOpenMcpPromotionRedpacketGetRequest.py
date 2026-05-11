from jd.api.base import RestApi

class UnionOpenMcpPromotionRedpacketGetRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.redPacketPromotionCodeReq = None

		def getapiname(self):
			return 'jd.union.open.mcp.promotion.redpacket.get'

		def get_version(self):
			return '1.0'
			
	

class RedPacketPromotionCodeReq(object):
		def __init__(self):
			"""
			"""
			self.openId = None






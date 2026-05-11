from jd.api.base import RestApi

class ImgzonePictureUploadRequest(RestApi):
		def __init__(self,domain='gw.api.360buy.com',port=80):
			"""
			"""
			RestApi.__init__(self,domain, port)
			self.image_data = None
			self.picture_cate_id = None
			self.picture_name = None

		def getapiname(self):
			return 'jingdong.imgzone.picture.upload'

			






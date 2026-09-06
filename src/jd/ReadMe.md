# python3 SDK 
## 1. dependencies
 - rsa
 - psutil
 - apscheduler
 - wincertstore （when SKD is using in windows environment）
## 2. how to use
### (1) use API
   The code fragment shows the basic use of an API, the main steps are first init an api, 
 and second to get the result
    
```
import jd.api
import json

jd.setDefaultAppInfo("your appKey", "your appSecret") # only need to init one time
# get a api you need to use
a = jd.api.AreaProvinceGetRequest('the domain this SDK will send request to', 80)
a.param = 'a'
f = a.getResponse("your access_token")
print(json.dumps(f, ensure_ascii=False))
```
   The Example show a simple use of the SDK, in python, we just declare the fist level vars of xxxRequesst,
 so for some complex structures, we didn't specify for you, you can constuct the field with json by you self, then 
 then use  xxxRequesst.xxx = json to set the request param.
    
### (2) security
```
from jd.security.tde_client.tde_client import TdeClientCache, TdeClient
tcc = TdeClientCache()
ins = tcc.instance("the domain this SDK will send request to", "access_token", "app_key", "app_secret")
# encryption
ciphertext = ins.encrypt_string('16612341234')
print(ciphertext)
# judge if the text is encrypted
if TdeClient.is_encrypt_data(ciphertext):
    # decryption
    print(ins.decrypt_string(ciphertext))
```
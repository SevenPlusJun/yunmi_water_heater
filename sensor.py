'''
v1.0
by seven
'''
import os, time
import logging, json
import requests, hashlib
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (ATTR_ATTRIBUTION, CONF_NAME)
import jsonpath
_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'yunmi water heater'
ATTRIBUTION = 'by seven'

CONF_PHONE_NUMBER = 'phone_number'
CONF_PASSWORD = 'password'
CONF_CLIENT_ID = 'client_id'

TOKEN_PATH = 'yunmi_water_heater.txt'
TOKEN_PATH = os.path.split(os.path.split(os.path.split(os.path.realpath(__file__))[0])[0])[0] + '/' + TOKEN_PATH

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PHONE_NUMBER): cv.string,
    vol.Required(CONF_PASSWORD): cv.string,
    vol.Required(CONF_CLIENT_ID): cv.string,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
})

def setup_platform(hass, config, add_devices, discovery_info=None):
    _LOGGER.info('setting up yunmi water heater')
    sensor = YunmiWaterHeaterSensor(
                            config.get(CONF_NAME),
                            config.get(CONF_PHONE_NUMBER),
                            config.get(CONF_PASSWORD),
                            config.get(CONF_CLIENT_ID)
                        )
    add_devices([sensor], True)


class YunmiWaterHeaterSensor(Entity):
    def __init__(self, name, phone_number, password, client_id):
        self._name = name
        self._client_id = client_id
        self._token = None
        self._phone_number = phone_number
        self._password = password
        self._access_token_exp_time = None
        self._detail = {}
        self._did = None
        self._isonline = None

        try:
            with open(TOKEN_PATH) as f:
                token_arr = json.loads(f.read())
                self._access_token = token_arr['access_token']
                self._refresh_token = token_arr['refresh_token']
                self._user_id = token_arr['user_id']
                self._member_id = token_arr['member_id']
        except:
            self._access_token = None
            self._refresh_token = None
            self._user_id = None
            self._member_id = None

    @property
    def name(self):
        return self._name

    @property
    def client_id(self):
        return self._client_id

    @property
    def did(self):
        return self._did
    
    @property
    def isOnline(self):
        return self._isonline
    

    @property
    def device_state_attributes(self):
        if self._detail is not None:
            return {
                'washStatus': self._detail['washStatus'],
                'velocity': self._detail['velocity'],
                'waterTemp': self._detail['waterTemp'],
                'targetTemp': self._detail['targetTemp'],
                'errStatus': self._detail['errStatus'],
                'hotWater': self._detail['hotWater'],
                'needClean': self._detail['needClean'],
                'modeType': self._detail['modeType'],
                'appointStart': self._detail['appointStart'],
                'appointEnd': self._detail['appointEnd'],
                #'update_time': self._update_time,
                ATTR_ATTRIBUTION: ATTRIBUTION
            }

    def yunmi_login(self):
        url = 'https://ms.viomi.com.cn//user-web/services/login/withPwd?account='+self._phone_number+'&pwd='+hashlib.md5(str(self._password).encode('utf-8')).hexdigest().upper()
        headers = { 'Accept':'application/json',
                    'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            self._refresh_token = res_list['mobBaseRes']['result']['token']
            self._usercode = res_list['mobBaseRes']['result']['userBaseInfo']['userCode']
            self._userId = str(res_list['mobBaseRes']['result']['userXiaomiInfo']['userId'])
            tk_arr = self.yunmi_get_access_token(self._refresh_token, self._client_id)
            if tk_arr:
                self._access_token = tk_arr['access_token']
                self._member_id = tk_arr['member_id']
            ret = {'refresh_token': self._refresh_token, 'user_id': self._user_id, 'access_token': self._access_token, 'member_id': self._member_id}
            with open(TOKEN_PATH, 'w') as f:
                f.write(json.dumps(ret))
            return True
        except Exception as e:
            _LOGGER.error('login failed：'+e.__context__)
            return False
        
    def yunmi_get_access_token(self, refresh_token, client_id):
        url = 'https://ms.viomi.com.cn/home/mi/getMiInfoByToken?token='+refresh_token+'&clientId='+client_id
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            self._access_token_exp_time = int(res_list['result']['expiresIn'])

            return {'access_token': res_list['result']['token'], 'member_id': str(res_list['result']['mid'])}
        except Exception as e:
            _LOGGER.error('get access token failed:'+e.__context__)
            return False


    def yunmi_get_detail(self):
        url = 'https://openapp.io.mi.com/openapp/device/rpc/274157014?data=%7B%22method%22:%22get_prop%22,%22did%22:%22274157014%22,%22id%22:%221%22,%22params%22:%5B%22washStatus%22,%22velocity%22,%22waterTemp%22,%22targetTemp%22,%22errStatus%22,%22hotWater%22,%22needClean%22,%22modeType%22,%22appointStart%22,%22appointEnd%22%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['code'] == 0:
                self._detail['washStatus'] = res_list['result'][0]
                self._detail['velocity'] = res_list['result'][1]
                self._detail['waterTemp'] = res_list['result'][2]
                self._detail['targetTemp'] = res_list['result'][3]
                self._detail['errStatus'] = res_list['result'][4]
                self._detail['hotWater'] = res_list['result'][5]
                self._detail['needClean'] = res_list['result'][6]
                self._detail['modeType'] = res_list['result'][7]
                self._detail['appointStart'] = res_list['result'][8]
                self._detail['appointEnd'] = res_list['result'][9]
            return True
        except Exception as e:
            _LOGGER.error('get detail failed:'+e)
            self._detail['washStatus'] = -99
            self._detail['velocity'] = -99
            self._detail['waterTemp'] = -99
            self._detail['targetTemp'] = -99
            self._detail['errStatus'] = -99
            self._detail['hotWater'] = -99
            self._detail['needClean'] = -99
            self._detail['modeType'] = -99
            self._detail['appointStart'] = -99
            self._detail['appointEnd'] = -99
            return False

    def yunmi_get_deviceid(self):
        url = 'https://openapp.io.mi.com/openapp/user/device_list?accessToken='+self._access_token+'&clientId='+self._client_id+'&locale=zh_CN'
        
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                self._did = res_list['result']['list'][0]['did']
                self._isonline = res_list['result']['list'][0]['isOnline']
                return True
        except Exception as e:
            _LOGGER.error('get deviceid failed:'+e)
            self._did = 0
            self._isonline =  'error'
            return False

    def update(self):
        '''scan interval default to be 30s'''
        _LOGGER.info("Updating the sensor...")
        try:
            if self._access_token_exp_time is not None and int(round(time.time() * 1000)) >= self._access_token_exp_time:
                self.yunmi_login()
            if self._access_token is not None :
                self.yunmi_get_detail()
                self.yunmi_get_deviceid()
            else:
                self.yunmi_login()
                self.yunmi_get_detail()   
                self.yunmi_get_deviceid()
        except Exception as e:
            _LOGGER.error("update _access_token fail"+e.__context__) 
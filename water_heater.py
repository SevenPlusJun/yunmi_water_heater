'''
v1.1
by seven
'''
import os, time
import logging, json
import requests, hashlib
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.temperature import display_temp as show_temp
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from typing import List
from homeassistant.const import (
    ATTR_ATTRIBUTION, 
    ATTR_ENTITY_ID, 
    ATTR_TEMPERATURE, 
    TEMP_CELSIUS,
    SERVICE_TURN_ON,
    SERVICE_TURN_OFF,
    PRECISION_WHOLE,
    PRECISION_TENTHS,)
import jsonpath
import functools as ft

from homeassistant.components.water_heater import (
    SUPPORT_OPERATION_MODE,
    SUPPORT_TARGET_TEMPERATURE,
    _LOGGER,
    ATTR_AWAY_MODE,
    ATTR_OPERATION_MODE,
    DOMAIN,
    SERVICE_SET_AWAY_MODE,
    SERVICE_SET_TEMPERATURE,
    SERVICE_SET_OPERATION_MODE,
    WaterHeaterDevice,
    PLATFORM_SCHEMA
)
from homeassistant.loader import bind_hass


_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'yunmi water heater'
ATTRIBUTION = 'by seven'

CONF_PHONE_NUMBER = 'phone_number'
CONF_PASSWORD = 'password'
CONF_CLIENT_ID = 'client_id'


ATTR_MAX_TEMP = "max_temp"
ATTR_MIN_TEMP = "min_temp"
ATTR_AWAY_MODE = "away_mode"
ATTR_OPERATION_MODE = "operation_mode"
ATTR_OPERATION_LIST = "operation_list"
ATTR_TARGET_TEMP_HIGH = "target_temp_high"
ATTR_TARGET_TEMP_LOW = "target_temp_low"
ATTR_CURRENT_TEMPERATURE = "current_temperature"
ATTR_HOT_WATER = "hot_water"
ATTR_ERROR_STATUS = "error_status"
ATTR_NEED_CLEAN = "need_clean"
ATTR_APPOINT_START = "appoint_start"
ATTR_APPOINT_END = "appoint_end"

STATE_APPOINTMENT = '预约'
STATE_QUICKBATH = '速热洗浴'
STATE_DAILYTEMPERATURE = '日常水温'
STATE_UNAVALIABLE = '不可用'
STATE_OFF = '关机'
STATE_ON = '开机'

HA_STATE_TO_YUNMI = {STATE_APPOINTMENT: 2, STATE_QUICKBATH: 1, STATE_DAILYTEMPERATURE: 0, STATE_OFF: -1 }
YUNMI_STATE_TO_HA = {v: k for k, v in HA_STATE_TO_YUNMI.items() if k != ""}

STATE_ATTRS_YUNMI = ["washStatus", "velocity", "waterTemp", "targetTemp", "errStatus", "hotWater", "needClean", "modeType", "appointStart", "appointEnd"]


TOKEN_PATH = 'yunmi_water_heater.txt'
TOKEN_PATH = os.path.split(os.path.split(os.path.split(os.path.realpath(__file__))[0])[0])[0] + '/' + TOKEN_PATH


SUPPORT_FLAGS_HEATER = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_PHONE_NUMBER): cv.string, vol.Required(CONF_PASSWORD): cv.string,  vol.Required(CONF_CLIENT_ID): cv.string }
)




async def async_setup(hass, config):
    """Set up water_heater devices."""
    component = hass.data[DOMAIN] = EntityComponent(
        _LOGGER, DOMAIN, hass, SCAN_INTERVAL
    )
    await component.async_setup(config)

    component.async_register_entity_service(
        SERVICE_SET_AWAY_MODE, SET_AWAY_MODE_SCHEMA, async_service_away_mode
    )
    component.async_register_entity_service(
        SERVICE_SET_TEMPERATURE, SET_TEMPERATURE_SCHEMA, async_service_temperature_set
    )
    component.async_register_entity_service(
        SERVICE_SET_OPERATION_MODE,
        SET_OPERATION_MODE_SCHEMA,
        "async_set_operation_mode",
    )
    component.async_register_entity_service(
        SERVICE_TURN_OFF, ON_OFF_SERVICE_SCHEMA, "async_turn_off"
    )
    component.async_register_entity_service(
        SERVICE_TURN_ON, ON_OFF_SERVICE_SCHEMA, "async_turn_on"
    )

    return True


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    _LOGGER.info('setting up yunmi water heater')    
    name = config.get('name') or DEFAULT_NAME
    phone_number = config.get('phone_number')
    password = config.get('password')
    client_id = config.get('client_id')

    _LOGGER.error('============= yunmi water heater setup -> name: %s =============', name)
    yunmi_wh = YunmiWaterHeater(hass, name, phone_number, password, client_id)
    async_add_entities([yunmi_wh], update_before_add=True)


class YunmiWaterHeaterController(object):
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
        
        
        _LOGGER.error('============= YunmiWaterHeaterController setup -> phone_number: %s =============', phone_number)


        try:
            with open(TOKEN_PATH) as f:
                token_arr = json.loads(f.read())
                self._access_token = token_arr['access_token']
                self._refresh_token = token_arr['refresh_token']
                self._user_id = token_arr['user_id']
                self._member_id = token_arr['member_id']
                _LOGGER.error('============= YunmiWaterHeaterController setup -> _access_token: %s =============', self._access_token)
        except:
            self._access_token = None
            self._refresh_token = None
            self._user_id = None
            self._member_id = None
        
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
            _LOGGER.error("update fail"+e.__context__) 

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
            self._userId = str(res_list['mobBaseRes']['result']['userViomiInfo']['userId'])
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
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22get_prop%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B%22washStatus%22,%22velocity%22,%22waterTemp%22,%22targetTemp%22,%22errStatus%22,%22hotWater%22,%22needClean%22,%22modeType%22,%22appointStart%22,%22appointEnd%22%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        
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

    def yunmi_set_temperature(self, temperature):
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22set_temp%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B'+str(int(temperature))+'%5D%7D&clientId='+str(self._client_id)+'&accessToken='+str(self._access_token)
         
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                return True
        except Exception as e:
            _LOGGER.error('yunmi_set_temperature failed:'+e)
            return False

    def yunmi_set_appoint(self,appointstart ,appointend):   
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22set_appoint%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B1,' + str(appointstart) + ',' + str(appointend) +'%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                return True
        except Exception as e:
            _LOGGER.error('yunmi_set_appoint failed:'+e)
            return False

    def yunmi_set_mode(self, modetype):   
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22set_mode%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B' + str(modetype) +'%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                return True
        except Exception as e:
            _LOGGER.error('yunmi_set_mode failed:'+e)
            return False

    def yunmi_set_poweron(self):
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22set_power%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B1%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                return True
        except Exception as e:
            _LOGGER.error('yunmi_set_poweron failed:'+e)
            return False

    def yunmi_set_poweroff(self):
        url = 'https://openapp.io.mi.com/openapp/device/rpc/' + str(self._did) + '?data=%7B%22method%22:%22set_power%22,%22did%22:%22' + str(self._did) + '%22,%22id%22:%221%22,%22params%22:%5B0%5D%7D&clientId='+self._client_id+'&accessToken='+self._access_token
        
        headers = { 'Accept-Encoding':'br, gzip, deflate',
                    'User-Agent':'WaterPurifier/2.1.6 (iPhone; iOS 12.2; Scale/3.00)'
                    }  
        try:
            res = requests.get(url, headers=headers)
            json_str = res.content.decode(encoding='utf-8')
            res_list = json.loads(json_str)
            if res_list['message'] == 'ok':
                return True
        except Exception as e:
            _LOGGER.error('yunmi_set_poweroff failed:'+e)
            return False
    
    async def update(self):
        '''scan interval default to be 30s'''
        _LOGGER.error("Updating the sensor...")
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
            _LOGGER.error("update fail"+e.__context__) 



class YunmiWaterHeater(WaterHeaterDevice):
    def __init__(self, hass, name: str, phone_number: str, password: str,
                 client_id: str) -> None:
        #super().__init__(self, name, phone_number, password, client_id)
        self._max_temp = 80.0
        self._min_temp = 30.0
        self._supported_features = SUPPORT_TARGET_TEMPERATURE | SUPPORT_OPERATION_MODE

        self._hass = hass
        self._name = name
        self._controller = YunmiWaterHeaterController(hass, phone_number, password, client_id)
        self._device_state_attrs = {}

    @property
    def min_temp(self):
        """Return the minimum temperature."""
        return self._min_temp

    @property
    def max_temp(self):
        """Return the maximum temperature."""
        return self._max_temp

    @property
    def state(self):
        """Return the current state."""
        if self._controller._detail['washStatus'] == 0:
            return STATE_OFF
        else:
            return YUNMI_STATE_TO_HA[self._controller._detail["modeType"]]

    @property
    def current_operation(self) -> str:
        """Return the current operating mode (Auto, On, or Off)."""
        if self._controller._detail['washStatus'] == 0:
            return STATE_OFF
        else:
            return YUNMI_STATE_TO_HA[self._controller._detail["modeType"]]

    @property
    def operation_list(self) -> List[str]:
        """Return the list of available operations."""
        return list(HA_STATE_TO_YUNMI)

    async def async_update(self) -> None:
        """Get the latest state data for a DHW controller."""
        await self._controller.update()
        for attr in STATE_ATTRS_YUNMI:
            self._device_state_attrs[attr] = self._controller._detail[attr]

    @property
    def precision(self):
        """Return the precision of the system."""
        #if self.hass.config.units.temperature_unit == TEMP_CELSIUS:
        #    return PRECISION_TENTHS
        return PRECISION_WHOLE

    @property
    def available(self):
        """Return if the the device is online or not."""
        return self._controller.isOnline

    @property
    def name(self):
        """Return the name of the water heater."""
        if self._name is None:
            self._name = "Hot Water"
        return self._name

    @property
    def current_temperature(self):
        """Return the current temperature."""
        return self._controller._detail['waterTemp']

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return self._controller._detail['targetTemp']

    @property
    def target_temperature_high(self):
        """Return the highbound target temperature we try to reach."""
        return None

    @property
    def target_temperature_low(self):
        """Return the lowbound target temperature we try to reach."""
        return None

    def set_temperature(self, **kwargs):
        """Set new target temperature."""
        target_temp = kwargs.get(ATTR_TEMPERATURE)
        if self._controller.yunmi_set_temperature(target_temp) is True:
            self._targetTemp = target_temp
        self.schedule_update_ha_state()
        return True
        #raise NotImplementedError()

    async def async_set_operation_mode(self, **kwargs):
        """Set new target operation mode."""
        current_operation = kwargs.get(ATTR_OPERATION_MODE)
        if current_operation == STATE_APPOINTMENT:
            self._controller.yunmi_set_poweron()
            if self._controller.yunmi_set_appoint(8,18) is True:
                self._curroperation = current_operation
            self.schedule_update_ha_state()
            return True
        elif current_operation == STATE_DAILYTEMPERATURE:
            self._controller.yunmi_set_poweron()
            if self._controller.yunmi_set_mode(HA_STATE_TO_YUNMI[current_operation]) is True:
                self._curroperation = current_operation
            self.schedule_update_ha_state()
            return True
        elif current_operation == STATE_QUICKBATH:
            self._controller.yunmi_set_poweron()
            if self._controller.yunmi_set_mode(HA_STATE_TO_YUNMI[current_operation])  is True:
                self._curroperation = current_operation
            self.schedule_update_ha_state()
            return True
        elif current_operation == STATE_OFF:
            if self._controller.yunmi_set_poweroff() is True:
                self._curroperation = current_operation
            self.schedule_update_ha_state()
            return True
        else:
            _LOGGER.error("set_operation_mode error")
            return False

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS
        

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_FLAGS_HEATER

    @property
    def hot_water(self):
        """Return the unit of measurement."""
        return str(self._controller._detail['hot_water'])+'%'
        

    @property
    def error_status(self):
        """Return the list of supported features."""
        return self._controller._detail['error_status']

    @property
    def need_clean(self):
        """Return the unit of measurement."""
        return self._controller._detail['need_clean']
        

    @property
    def appoint_start(self):
        """Return the list of supported features."""
        return str(self._controller._detail['appoint_start'])+'点'    
    
    @property
    def appoint_end(self):
        """Return the list of supported features."""
        return str(self._controller._detail['appoint_end'])+'点'   

    async def async_turn_on(self):
        if self._controller._detail['washStatus'] == 1:
            return True
        elif self._controller._detail['washStatus'] == 0:
            self._controller.yunmi_set_poweron()
            return True
        else:
            _LOGGER.error("async_turn_on error")
            return False
    
    async def async_turn_off(self):
        if self._controller._detail['washStatus'] == 0:
            return True
        elif self._controller._detail['washStatus'] == 1:
            self._controller.yunmi_set_poweroff()
            return True
        else:
            _LOGGER.error("async_turn_off error")
            return False


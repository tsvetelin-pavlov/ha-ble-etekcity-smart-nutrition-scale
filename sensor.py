import logging
import asyncio
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import UnitOfMass
from homeassistant.const import UnitOfVolume
from homeassistant.core import callback
from bleak import BleakClient
from bleak.exc import BleakError
from struct import unpack
from enum import Enum
from collections import namedtuple

_LOGGER = logging.getLogger(__name__)

"""
From https://github.com/hertzg/metekcity.
Communication happens on service 0x1910, device to client communication happens on 0x2c12 characteristic and client to device communication on 0x2c12.
Service: 00001910-0000-1000-8000-00805f9b34fb
    Characteristic: 00002c10-0000-1000-8000-00805f9b34fb [READ]
    Characteristic: 00002c11-0000-1000-8000-00805f9b34fb [WRITEWITHOUTRESPONSE, WRITE]
    Characteristic: 00002c12-0000-1000-8000-00805f9b34fb [NOTIFY, INDICATE]
Service: 0000180a-0000-1000-8000-00805f9b34fb
    Characteristic: 00002a23-0000-1000-8000-00805f9b34fb [READ]
    Characteristic: 00002a50-0000-1000-8000-00805f9b34fb [READ]
Service: 00001800-0000-1000-8000-00805f9b34fb
    Characteristic: 00002a00-0000-1000-8000-00805f9b34fb [READ]
    Characteristic: 00002a01-0000-1000-8000-00805f9b34fb [READ]
"""

#WRITE_CHAR = "00002c11-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR = "00002c12-0000-1000-8000-00805f9b34fb"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the Etekcity Smart Nutrition Scale sensor from a config entry."""
    address = config_entry.data["address"]
    _LOGGER.debug(f"Setting up Etekcity Smart Nutrition Scale sensor with address: {address}")
    scale = EtekcitySmartNutritionScaleSensor(hass, address)
    async_add_entities([scale], True)

class EtekcitySmartNutritionScaleSensor(SensorEntity):
    def __init__(self, hass, address):
        self.hass = hass
        self._address = address
        self._state = None
        self._available = False
        self._attr_name = "Etekcity Smart Nutrition Scale Weight"
        self._attr_unique_id = f"etekcity_smart_nutrition_scale_{self._address}"
        self._client = None
        self._disconnect_timer = None
        self._connect_lock = asyncio.Lock()
        self._connection_retry_interval = 60  # Retry connection every 60 seconds
        self._retry_task = None
        self._unit = None  # Add this line to store the unit
        _LOGGER.debug(f"EtekcitySmartNutritionScaleSensor initialized with address: {address}")

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def state(self):
        return self._state

    @property
    def unit_of_measurement(self):
        if self._unit is None:
            return None
        unit_mapping = {
            self.Unit.GRAMS: UnitOfMass.GRAMS,
            self.Unit.ML: UnitOfVolume.MILLILITERS,
            self.Unit.ML_MILK: UnitOfVolume.MILLILITERS,
            self.Unit.FLOZ: UnitOfVolume.FLUID_OUNCES,
            self.Unit.FLOZ_MILK: UnitOfVolume.FLUID_OUNCES,
            self.Unit.OZ: UnitOfMass.OUNCES,
            self.Unit.LBOZ: "lb:oz"
        }
        return unit_mapping.get(self._unit, None)

    @property
    def available(self):
        return self._available
    
    class Unit(Enum):
        GRAMS = 0x00
        ML = 0x02
        ML_MILK = 0x04
        FLOZ = 0x03
        FLOZ_MILK = 0x05
        OZ = 0x06
        LBOZ = 0x01

    WeightData = namedtuple('WeightData', ['weight', 'unit', 'is_stable'])

    def decode_weight(self, data):
        """Decode weight data for Etekcity Smart Nutrition Scale and return a structure with weight, unit, and is_stable."""
        _LOGGER.debug(f"Decoding weight data: {data.hex()}")

        # Extract relevant data from bytes
        sign = data[9] == 0x01     # Sign byte (True if negative, False if positive)
        weight_raw = data[10:12]   # Weight bytes (10 and 11)
        unit = self.Unit(data[12]) # Unit byte
        is_stable = data[13] == 0x01  # Stability byte (True if stable, False if measuring)

        # Convert the raw weight to the appropriate unit with big-endian byte order
        weight_raw_value = int.from_bytes(weight_raw, byteorder="big")
        
        if unit == self.Unit.LBOZ:
            # Convert to pounds and ounces
            pounds = weight_raw_value // 16
            ounces = weight_raw_value % 16 / 10
            weight = f"{pounds}:{ounces:.1f}"
            if sign:
                weight = f"-{weight}"
        else:
            # Apply sign and convert to grams or ounces
            divisor = 100 if unit in {self.Unit.FLOZ, self.Unit.FLOZ_MILK, self.Unit.OZ, self.Unit.LBOZ} else 10
            weight = weight_raw_value / divisor if not sign else -weight_raw_value / divisor

        # Determine if the measurement is stable
        if not is_stable:
            _LOGGER.debug("Measurement is unstable. Weight not returned.")
            return None  # Return None if the measurement is not stable

        _LOGGER.debug(f"Stable weight measurement: {weight}, Unit: {unit.name}, Stable: {is_stable}")
        return self.WeightData(weight=weight, unit=unit, is_stable=is_stable)

    def notification_handler(self, sender, data):
        _LOGGER.debug(f"Received notification: {data.hex()}")
        weight_data = self.decode_weight(data)
        if weight_data:
            self._state = weight_data.weight
            self._unit = weight_data.unit  # Store the unit
            self._available = True
            _LOGGER.info(f"Updated weight: {self._state}, Unit: {weight_data.unit.name}, Stable: {weight_data.is_stable}")
            self.async_write_ha_state()
        
        # Reset the disconnect timer
        if self._disconnect_timer:
            self._disconnect_timer.cancel()
        self._disconnect_timer = self.hass.loop.call_later(60, self.disconnect)

    async def connect(self):
        async with self._connect_lock:
            if self._client and self._client.is_connected:
                return

            try:
                self._client = BleakClient(self._address, timeout=10.0)
                await asyncio.wait_for(self._client.connect(), timeout=20.0)
                _LOGGER.debug(f"Connected to Etekcity Smart Nutrition Scale: {self._address}")
                self._available = True
                
                await self._client.start_notify(NOTIFY_CHAR, self.notification_handler)
                _LOGGER.debug(f"Notifications started for characteristic: {NOTIFY_CHAR}")
                
                #await self._client.write_gatt_char(WRITE_CHAR, b'\x01', response=False)
                #_LOGGER.debug(f"Wrote to characteristic: {WRITE_CHAR}")
                
                # Set initial disconnect timer
                self._disconnect_timer = self.hass.loop.call_later(60, self.disconnect)
            
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout connecting to Etekcity Smart Nutrition Scale: {self._address}")
                self._available = False
                self._schedule_retry()
            except BleakError as e:
                _LOGGER.error(f"Error connecting to Etekcity Smart Nutrition Scale: {e}")
                self._available = False
                self._schedule_retry()
            except Exception as e:
                _LOGGER.error(f"Unexpected error connecting to Etekcity Smart Nutrition Scale: {e}")
                self._available = False
                self._schedule_retry()

    @callback
    def _schedule_retry(self):
        if self._retry_task:
            self._retry_task.cancel()
        self._retry_task = self.hass.async_create_task(self._retry_connect())

    async def _retry_connect(self):
        await asyncio.sleep(self._connection_retry_interval)
        await self.async_update()

    def disconnect(self):
        if self._client and self._client.is_connected:
            asyncio.create_task(self._disconnect())

    async def _disconnect(self):
        try:
            await self._client.disconnect()
            _LOGGER.debug(f"Disconnected from Etekcity Smart Nutrition Scale: {self._address}")
        except Exception as e:
            _LOGGER.error(f"Error disconnecting from Etekcity Smart Nutrition Scale: {e}")
        finally:
            self._client = None
            self._available = False
            self.async_write_ha_state()

    async def async_added_to_hass(self):
        """Run when entity about to be added to hass."""
        await self.async_update()

    async def async_will_remove_from_hass(self):
        """Run when entity will be removed from hass."""
        if self._retry_task:
            self._retry_task.cancel()
        await self._disconnect()

    async def async_update(self):
        """Update the sensor."""
        if not self._client or not self._client.is_connected:
            await self.connect()

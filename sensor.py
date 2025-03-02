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
from .const import NAME, DOMAIN, RETRY_INTERVAL, DISCONNECT_TIMEOUT

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

NOTIFY_CHAR = "00002c12-0000-1000-8000-00805f9b34fb"

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the sensor from a config entry."""
    address = config_entry.data["address"]
    _LOGGER.debug(f"Setting up {NAME} sensor with address: {address}")
    scale = EtekcitySmartNutritionScaleSensor(hass, address)
    async_add_entities([scale], True)

class Units(Enum):
    GRAMS = 0x00
    ML = 0x02
    ML_MILK = 0x04
    FLOZ = 0x03
    FLOZ_MILK = 0x05
    OZ = 0x06
    LBOZ = 0x01

class PacketTypes(Enum):
    SET_UNIT = 0xc0
    SET_TARE = 0xc1
    SET_AUTO_OFF = 0xc4
    MEASUREMENT = 0xd0
    UNIT_STATE = 0xd1
    TARE_STATE = 0xd3
    AUTO_OFF_STATE = 0xd5
    ERROR_STATE = 0xe0
    ITEM_STATE = 0xe4
    SET_NUTRITION = 0xc2
    PING = 0xc3
    UNKNOWN_D2 = 0xd2
    PONG = 0xd4
    UNKNOWN_E1 = 0xe1
    UNKNOWN_E2 = 0xe2
    UNKNOWN_E3 = 0xe3

WeightData = namedtuple('WeightData', ['weight', 'unit', 'is_stable'])

class EtekcitySmartNutritionScaleSensor(SensorEntity):
    def __init__(self, hass, address):
        self.hass = hass
        self._address = address
        self._state = None
        self._available = False
        self._attr_name = f"{NAME} Weight"
        self._attr_unique_id = f"{DOMAIN}_{self._address}"
        self._client = None
        self._disconnect_timer = None
        self._connect_lock = asyncio.Lock()
        self._connection_retry_interval = RETRY_INTERVAL  # Retry connection every RETRY_INTERVAL seconds
        self._retry_task = None
        self._unit = None  # Add this line to store the unit
        _LOGGER.debug(f"{NAME} sensor initialized with address: {address}")

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
            Units.GRAMS: UnitOfMass.GRAMS,
            Units.ML: UnitOfVolume.MILLILITERS,
            Units.ML_MILK: UnitOfVolume.MILLILITERS,
            Units.FLOZ: UnitOfVolume.FLUID_OUNCES,
            Units.FLOZ_MILK: UnitOfVolume.FLUID_OUNCES,
            Units.OZ: UnitOfMass.OUNCES,
            Units.LBOZ: "lb:oz"
        }
        return unit_mapping.get(self._unit, None)

    @property
    def available(self):
        return self._available
    
    def decode_weight(self, data):
        """Decode weight data and return a structure with weight, unit, and is_stable."""

        packetType = data[4]

        # Ensure the packet is measurement
        if packetType != PacketTypes.MEASUREMENT.value:
            _LOGGER.debug(f"Packet is not of type MEASUREMENT: {packetType:#04x}")
            return None
            
        # Ensure the data has the expected length
        if len(data) != 12:
            _LOGGER.debug(f"Received data is not 12 bytes: {data.hex()}. It is {len(data)} bytes.")
            return None

        # Extract relevant data from bytes
        sign = data[6] == 0x01          # Sign byte (True if negative, False if positive)
        weight_raw = data[7:9]          # Weight bytes (10 and 11)
        unit = Units(data[9])           # Unit byte
        is_stable = data[10] == 0x01    # Stability byte (True if stable, False if measuring)

        # Convert the raw weight to the appropriate unit with big-endian byte order
        weight_raw_value = int.from_bytes(weight_raw, byteorder="big")
        
        # Apply sign and convert to grams or ounces
        divisor = 100 if unit in {Units.FLOZ, Units.FLOZ_MILK, Units.OZ, Units.LBOZ} else 10
        weight = weight_raw_value / divisor if not sign else -weight_raw_value / divisor

        if unit == Units.LBOZ:
            # Convert to pounds and ounces
            pounds = int(weight / 16)
            ounces = weight % 16
            weight = f"{pounds} : {ounces:.1f}"

        # Determine if the measurement is stable
        if not is_stable:
            _LOGGER.debug("Measurement is unstable. Weight not returned.")
            return None  # Return None if the measurement is not stable

        _LOGGER.debug(f"Stable weight measurement: {weight}, Unit: {unit.name}, Stable: {is_stable}")
        return WeightData(weight=weight, unit=unit, is_stable=is_stable)

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
        self._disconnect_timer = self.hass.loop.call_later(DISCONNECT_TIMEOUT, self.disconnect)

    async def connect(self):
        async with self._connect_lock:
            if self._client and self._client.is_connected:
                return

            try:
                self._client = BleakClient(self._address, timeout=10.0)
                await asyncio.wait_for(self._client.connect(), timeout=20.0)
                _LOGGER.debug(f"Connected to {NAME}: {self._address}")
                self._available = True
                
                await self._client.start_notify(NOTIFY_CHAR, self.notification_handler)
                _LOGGER.debug(f"Notifications started for characteristic: {NOTIFY_CHAR}")
                
                # Set initial disconnect timer
                self._disconnect_timer = self.hass.loop.call_later(DISCONNECT_TIMEOUT, self.disconnect)
            
            except asyncio.TimeoutError:
                _LOGGER.error(f"Timeout connecting to {NAME}: {self._address}")
                self._available = False
                self._schedule_retry()
            except BleakError as e:
                _LOGGER.error(f"Error connecting to {NAME}: {e}")
                self._available = False
                self._schedule_retry()
            except Exception as e:
                _LOGGER.error(f"Unexpected error connecting to {NAME}: {e}")
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
            _LOGGER.debug(f"Disconnected from {NAME}: {self._address}")
        except Exception as e:
            _LOGGER.error(f"Error disconnecting from {NAME}: {e}")
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

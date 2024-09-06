from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components import bluetooth
from homeassistant.const import Platform

DOMAIN = "ble_scale"
PLATFORMS = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BLE Scale from a config entry."""
    address = entry.data["address"]

    def _device_update(
        service_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Handle device updates."""
        pass  # We'll handle updates in the sensor component

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _device_update,
            {"address": address},
            bluetooth.BluetoothScanningMode.PASSIVE
        )
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

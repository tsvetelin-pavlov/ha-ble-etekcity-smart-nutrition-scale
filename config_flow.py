from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_ADDRESS
import voluptuous as vol
from .const import DOMAIN, NAME

class EtekcitySmartNutritionScaleConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        self.discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        errors = {}
        
        # Get discovered devices
        for discovery_info in async_discovered_service_info(self.hass):
            address = discovery_info.address
            self.discovered_devices[address] = discovery_info

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{NAME} ({address})",
                data=user_input,
            )

        device_list = {
            address: f"{info.name} ({address})" if info.name else address
            for address, info in self.discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(device_list),
            }),
            errors=errors,
        )

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> FlowResult:
        """Handle the bluetooth discovery step."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self.discovered_devices[discovery_info.address] = discovery_info
        return await self.async_step_user()

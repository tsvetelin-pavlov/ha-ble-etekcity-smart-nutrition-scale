# BLE Scale Custom Component for Home Assistant

This custom component integrates Bluetooth Low Energy (BLE) scales into Home Assistant, providing real-time weight measurements.

## Features

- Real-time weight measurements from BLE scales
- Automatic connection and reconnection handling
- Configurable through the Home Assistant UI

## Requirements

- Home Assistant version 2023.3.0 or newer
- A compatible BLE scale (tested with [https://www.aliexpress.com/item/1005006441099756.html?spm=a2g0o.productlist.main.1.47d4FdsNFdsNoF&algo_pvid=0a887cd2-c20a-47c9-8b0e-dafef7cbc300&algo_exp_id=0a887cd2-c20a-47c9-8b0e-dafef7cbc300-0&pdp_npi=4%40dis%21GBP%2123.23%218.48%21%21%21210.79%2176.99%21%402103894417256398161495877ec38b%2112000037224421583%21sea%21UK%210%21ABX&curPageLogUid=QsSqHi5ValiA&utparam-url=scene%3Asearch%7Cquery_from%3A])
- The BLE scale should be within range of your Home Assistant instance / Bluetooth Proxies

## Installation

### HACS (Recommended)

1. Ensure that [HACS](https://hacs.xyz/) is installed in your Home Assistant instance.
2. In the HACS panel, go to "Integrations".
3. Click the "+" button and search for "BLE Scale".
4. Click "Install" on the BLE Scale integration.
5. Restart Home Assistant.

### Manual Installation

1. Download the `ble_scale` directory from this repository.
2. Place the downloaded `ble_scale` directory in your Home Assistant's `custom_components` directory.
3. Restart Home Assistant.

## Configuration

1. In Home Assistant, go to Configuration > Integrations.
2. Click the "+" button to add a new integration.
3. Search for "BLE Scale" and select it.
4. Follow the configuration steps:
   - Select your BLE scale from the list of discovered devices.
   - If your scale is not automatically discovered, you can manually enter its Bluetooth address.

## Usage

Once configured, the BLE Scale will appear as a sensor entity in Home Assistant. The entity will be named "BLE Scale Weight" by default.

You can use this sensor in automations, scripts, or display it on your dashboard like any other Home Assistant sensor.

Example usage in an automation:

```yaml
automation:
  - alias: "Notify when weight is measured"
    trigger:
      platform: state
      entity_id: sensor.ble_scale_weight
    action:
      service: notify.pushbullet
      data:
        message: "New weight measurement: {{ states('sensor.ble_scale_weight') }} grams"
```

## Troubleshooting

- If the scale is not connecting, ensure it's within range and powered on.
- Check the Home Assistant logs for any error messages related to the BLE Scale component.
- If you're having persistent issues, try removing the integration and setting it up again.

## Contributing

Contributions to improve the BLE Scale component are welcome! Please submit issues and pull requests on the GitHub repository.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Thanks to the Home Assistant community for their support and inspiration.
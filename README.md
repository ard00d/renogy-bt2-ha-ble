# Renogy-bt2-ha-ble

A Home Assistant (MQTT) integration for the Renogy BT-2 bluetooth module. Tested with the Renogy DCC50S.


## Background

I wanted a quick way to monitor my Renogy DCC50S with Home Assistant, using my existing BT-2 bluetooth module. I was unable to find an existing integration, but found [neilsheps Arduino library](https://github.com/neilsheps/Renogy-BT2-Reader), with an excellent description of the reverse engineered protocol. That documentation made it relatively easy to write my own version, using Python and MQTT, to integrate with HA.

## Notice

This code is provided as-is. I've only tested with my own DCC50S, with Home Assistant running on a Raspberry Pi 4B, with an external USB bluetooth dongle.

I wrote this for myself, and consider the code "good enough" for my purposes. But, it could most likely be improved a bit.

I'm just sharing in case anyone else finds this useful, or as a good starting point for modding it to work with other BT-2 compatible devices.

## Install

1. Download/Clone the code and create a Python virtual environment in the src directory
   ```
   $ python -m venv venv
   $ source venv/bin/activate
   $ pip install -r requirements.txt
   ```

2. Edit the `config.py` file. Add your MQTT information, and the MAC address for your BT-2 module. You can use one of the various BLE scanner apps available on your phone to find the address. 

3. Test the script to see if it is working. If everything is good, it will publish MQTT autodiscovery info to Home Assistant, and you should see a new device under the MQTT integration.
    ```
    $ ./bt2.py --debug
    ```

4. Run the script as a systemd service, for continous updates.

   1. Edit the paths of *'WorkingDirectory'* and *'ExecStart'* in the `ha-bt2.service` file to match your installation
   2. Copy the `ha-bt2.service` file to `/etc/systemd/system/`
   3. Enable the service to start on boot 
   ```
   $ sudo systemctl daemon-reload
   $ sudo systemctl enable ha-bt2.service
   ```
   4. Start the service
   ```
   $ sudo systemctl start ha-bt2.service
   ```
## License

[GPLv3](LICENSE)

#!/usr/bin/env python
"""
This program is free software: you can redistribute it and/or modify it unde
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but 
WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or 
FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for 
more details.

You should have received a copy of the GNU General Public License along 
with this program. If not, see <https://www.gnu.org/licenses/>.

For hangs:
  'hcitool con'
  'hcitool ledc'  (disconnect LE connection)
"""

import asyncio
import json
import argparse
import traceback
import logging
import signal
import time
import yaml

from bleak import BleakScanner, BleakClient, BleakError
import paho.mqtt.publish as publish
import config


class BT2Data:
    def __init__(self) -> None:
        pass


class BT2Info:

    ADDR = config.BT2_ADDR

    # TX_SERVICE = "0000ffd0-0000-1000-8000-00805f9b34fb"
    # Tx characteristic. Sends data to the BT2
    TX_CHARACTERISTIC = "0000ffd1-0000-1000-8000-00805f9b34fb"

    # RX_SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"  # Rx service
    # Rx characteristic. Receives notifications from the BT2
    RX_CHARACTERISTIC = "0000fff1-0000-1000-8000-00805f9b34fb"

    REQUEST_DATA = b"\xFF\x03\x01\x00\x00\x23\x10\x31"  # query registers; get 35 bytes starting at 0x100

    def __init__(self) -> None:
        self.data = BT2Data()
        self.bt_device = None
        self.name = None
        self.addr = self.ADDR
        self.discovery_info_sent = False

    def _add_signal_handlers(self):
        loop = asyncio.get_event_loop()

        async def shutdown(sig):
            """
            Cancel all running async tasks (other than this one) when called.
            By catching asyncio.CancelledError, any running task can perform
            any necessary cleanup when it's cancelled.
            """
            tasks = []
            for task in asyncio.all_tasks(loop):
                if task is not asyncio.current_task(loop):
                    task.cancel()
                    tasks.append(task)
            results = await asyncio.gather(*tasks, return_exceptions=True)
            loop.stop()

        for sig in [signal.SIGINT, signal.SIGTERM]:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(sig)))

    def locate_device(self):
        asyncio.run(self._locate_device())

    async def _locate_device(self):
        self.bt_device = await BleakScanner.find_device_by_address(self.addr)
        if self.bt_device is None:
            raise Exception(
                "Couldn't find BLE device - is it in range? is another client connected? "
                + " Check 'hcitool con' and force disconnect if necessary"
            )
        self.name = self.bt_device.name
        self.addr = self.bt_device.address
        logger.info(
            "Located BT2 device - name=%s addr=%s",
            self.bt_device.name,
            self.bt_device.address,
        )

    def start_loop(self, interval):
        try:
            asyncio.run(self._query_loop(interval))
        except asyncio.CancelledError:
            logger.info("Caught signal and shutdown.")


    async def _query_loop(self, interval):
        self._add_signal_handlers()

        async with BleakClient(self.bt_device, timeout=20) as client:
            await client.start_notify(self.RX_CHARACTERISTIC, callback=self._callback)
            while True:
                try:
                    if not client.is_connected:
                        logger.warning("No connection...Attempting to reconnect")
                        await client.connect()
                        await client.start_notify(
                            self.RX_CHARACTERISTIC, callback=self._callback
                        )

                    await client.write_gatt_char(
                        self.TX_CHARACTERISTIC, self.REQUEST_DATA, False
                    )

                except EOFError:
                    logger.warning("DBus EOFError")
                except asyncio.exceptions.TimeoutError:
                    logger.warning("asyncio TimeOutError communicating with device")
                except BleakError as err:
                    logger.warning("BleakError - %s", err)
                except Exception as err:
                    logger.warning(
                        f"Error querying BT-2: {err}, {type(err)}"
                        + traceback.format_exc()
                    )

                if not interval:  # one-shot run, don't loop
                    break

                await asyncio.sleep(interval)

    def _callback(self, sender, data):
        logger.debug("DEBUG: DATA=%s", data.hex())

        self.data.aux_batt_v = int.from_bytes(data[5:7], byteorder="big") / 10
        self.data.combined_charging_amps = int.from_bytes(data[7:9], byteorder="big") / 100
        self.data.controller_temp = int.from_bytes(data[9:10], byteorder="big", signed=True)
        self.data.battery_temp = int.from_bytes(data[10:11], byteorder="big", signed=True)
        self.data.alternator_v = int.from_bytes(data[11:13], byteorder="big") / 10 #104h
        self.data.alternator_charging_amps = int.from_bytes(data[13:15], byteorder="big") / 100
        self.data.alternator_charging_watts = int.from_bytes(data[15:17], byteorder="big")
        self.data.solar_v = int.from_bytes(data[17:19], byteorder="big") / 10
        self.data.solar_charging_amps = int.from_bytes(data[19:21], byteorder="big") / 100
        self.data.combined_charging_watts = int.from_bytes(data[21:23], byteorder="big")
        # 10AH reserved
        self.data.aux_batt_v_lowest_day = int.from_bytes(data[25:27], byteorder="big") / 10
        self.data.aux_batt_v_highest_day = int.from_bytes(data[27:29], byteorder="big") / 10
        self.data.charging_amps_highest_day = int.from_bytes(data[29:31], byteorder="big") / 100
        # 10eh reserved
        self.data.input_power_highest_day =  int.from_bytes(data[33:35], byteorder="big")
        # 110h reserved
        self.data.accumulated_ah_day = int.from_bytes(data[37:39], byteorder="big")
        # 112h reserved
        self.data.generated_power_day = int.from_bytes(data[41:43], byteorder="big")
        # 114h reserved
        self.data.total_working_days = int.from_bytes(data[45:47], byteorder="big")
        self.data.total_over_discharged_count = int.from_bytes(data[47:49], byteorder="big")
        self.data.total_fully_charged_count = int.from_bytes(data[49:51], byteorder="big")
        self.data.accumulated_ah_aux_batt = int.from_bytes(data[51:55], byteorder="big")
        # 11a, 11b reserved
        self.data.accumulated_generated_watts = int.from_bytes(data[59:63], byteorder="big")
        # 11e, 11f reserved
        # 120 high 8 bits reserved
        self.data.charging_state = bin(int.from_bytes(data[68:69], byteorder="big"))
        self.data.error_bits_1 = bin(int.from_bytes(data[69:71], byteorder="big"))
        self.data.error_bits_2 = bin(int.from_bytes(data[71:73], byteorder="big"))

        # Add locally calculated sensor(s)
        self.data.solar_input_watts = int(
            self.data.solar_charging_amps * self.data.solar_v
        )

        # Publish Home Assistant discovery info to MQTT on first run
        if self.discovery_info_sent is False:
            msg = "Publishing Discovery information to Home Assistant"
            logger.info(msg)

            f = open("bt2_mqtt.yaml", "r")
            y = yaml.safe_load(f)
            for entry in y:
                if not "unique_id" in entry:
                    entry["unique_id"] = entry["object_id"] # required for mapping to a device
                if not "platform" in entry:
                    entry["platform"] = "mqtt"
                if not "expire_after" in entry:
                    entry["expire_after"] = 90
                if not "state_topic" in entry:
                    entry["state_topic"] = f"renogy-bt2/{entry['unique_id']}"
                if not "device" in entry:
                    entry["device"] = {"name": "Renogy DCC50S", "identifiers": bt2.name}

                logger.debug(
                    f"DISCOVERY_PUB=homeassistant/sensor/{entry['object_id']}/config\n"
                    + "PL={json.dumps(entry)}\n"
                )
                publish.single(
                    topic=f"homeassistant/sensor/{entry['object_id']}/config",
                    payload=json.dumps(entry),
                    retain=True,
                    hostname=config.MQTT_HOST,
                    auth=auth,
                )

            self.discovery_info_sent = True

        # Combine sensor updates for MQTT
        mqtt_msgs = []
        for k, v in bt2.data.__dict__.items():
            mqtt_msgs.append({"topic": f"renogy-bt2/bt2_{k}", "payload": v})
            if not args.quiet:
                print(f"{k} = {v}")

        publish.multiple(mqtt_msgs, hostname=config.MQTT_HOST, auth=auth)
        logger.info("Published updated sensor stats to MQTT")



if hasattr(config, "BT2_LOG_FILE"):
    logging.basicConfig(
        filename=config.BT2_LOG_FILE,
        format="%(asctime)s %(levelname)s:%(message)s",
        encoding="utf-8",
        level=logging.WARNING,
    )
logger = logging.getLogger("Renogy BT-2")
logger.setLevel(logging.INFO)

auth = {"username": config.MQTT_USER, "password": config.MQTT_PASS}

parser = argparse.ArgumentParser()
parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
parser.add_argument(
    "-i",
    "--interval",
    type=int,
    help="Run nonstop and query the device every <interval> seconds",
)
parser.add_argument(
    "-q", "--quiet", action="store_true", help="Quiet mode. No output except for errors"
)
args = parser.parse_args()


if args.debug:
    logger.warning("Setting logging level to DEBUG")
    logger.setLevel(logging.DEBUG)

if not args.quiet:
    logger.addHandler(logging.StreamHandler())


logger.info("Starting up")
bt2 = BT2Info()
while bt2.bt_device is None:
    try:
        bt2.locate_device()
    except Exception as err:
        logger.warning(f"Error searching for BT-2: {err}, {type(err)}")
    time.sleep(5)

bt2.start_loop(args.interval)



"""
Plant Monitor - IoT Plant Sensor System

A comprehensive plant monitoring system using Raspberry Pi Pico WH that tracks
environmental conditions and publishes data to Home Assistant via MQTT.

Features:
- Temperature and humidity monitoring (DHT11 sensor)
- Light level measurement (BH1750 sensor)
- Soil moisture monitoring (capacitive sensor)
- Local display (SSD1306 OLED)
- WiFi connectivity with auto-reconnect
- MQTT communication with Home Assistant discovery
- Error handling and sensor failure tracking
- Memory management and garbage collection

Hardware Requirements:
- Raspberry Pi Pico WH
- DHT11 temperature/humidity sensor
- BH1750 light sensor
- Capacitive soil moisture sensor
- SSD1306 OLED display
- Breadboard and jumper wires

Author: Nils Olivier (no222jk)
Course: 1DT305 IoT Summer Course, Linnaeus University
Year: 2025
"""

from machine import Pin, SoftI2C, ADC
import dht
from bh1750 import BH1750
import ssd1306
import time
import network
from umqtt.robust import MQTTClient
import json
import gc

# Import configuration
try:
    from config import *
except ImportError:
    print("config.py not found! Please create config.py with your settings.")
    print("See README.md for configuration instructions.")
    raise

# Use configuration values
ssid = WIFI_SSID
password = WIFI_PASSWORD
mqtt_broker = MQTT_BROKER
mqtt_port = MQTT_PORT
mqtt_user = MQTT_USERNAME
mqtt_password = MQTT_PASSWORD
client_id = MQTT_CLIENT_ID

PUBLISH_INTERVAL = PUBLISH_INTERVAL
SENSOR_READ_INTERVAL = SENSOR_READ_INTERVAL
STATUS_UPDATE_INTERVAL = STATUS_UPDATE_INTERVAL

# Global variables for sensors
oled = None
light_sensor = None
dht_sensor = None
soil_moisture_adc = None
wlan = None
mqtt_client = None

# Status tracking variables
sensor_status = {"dht11": False, "bh1750": False, "soil_moisture": False, "oled": False}
failed_sensor_reads = {"dht11": 0, "bh1750": 0, "soil_moisture": 0}
connection_status = {"wifi": False, "mqtt": False, "last_successful_publish": 0}


def initialize_sensors():
    """
    Initialize all sensors and update their status.

    Sets up I2C communication for BH1750 light sensor and OLED display,
    initializes DHT11 temperature/humidity sensor, and configures ADC for
    soil moisture readings. Updates global sensor_status dictionary to track
    which sensors are working properly.

    Returns:
        None
    """
    global oled, light_sensor, dht_sensor, soil_moisture_adc, i2c

    # Initialize I2C
    print("Initializing I2C...")
    i2c = SoftI2C(scl=Pin(PIN_I2C_SCL), sda=Pin(PIN_I2C_SDA), freq=400000)
    print("I2C devices found:", [hex(addr) for addr in i2c.scan()])

    # OLED setup
    print("Setting up OLED...")
    try:
        oled = ssd1306.SSD1306_I2C(128, 64, i2c)
        oled.fill(0)
        oled.text("Starting...", 0, 0)
        oled.show()
        print("OLED initialized successfully")
        sensor_status["oled"] = True
    except Exception as e:
        print("OLED initialization failed:", e)
        oled = None
        sensor_status["oled"] = False
    time.sleep(1)

    # BH1750 setup
    print("Setting up BH1750...")
    try:
        light_sensor = BH1750(bus=i2c, addr=0x23)
        test_lux = light_sensor.luminance(BH1750.CONT_HIRES_1)
        print("BH1750 initialized successfully, test reading:", test_lux)
        sensor_status["bh1750"] = True
    except Exception as e:
        print("BH1750 initialization failed:", e)
        light_sensor = None
        sensor_status["bh1750"] = False
    time.sleep(1)

    # DHT11 setup
    print("Setting up DHT11...")
    try:
        dht_sensor = dht.DHT11(Pin(PIN_DHT11))
        print("DHT11 initialized successfully")
        sensor_status["dht11"] = True
    except Exception as e:
        print("DHT11 initialization failed:", e)
        dht_sensor = None
        sensor_status["dht11"] = False
    time.sleep(1)

    # Soil moisture setup
    print("Setting up soil moisture sensor...")
    try:
        soil_moisture_adc = ADC(PIN_SOIL_MOISTURE)
        test_moisture = soil_moisture_adc.read_u16()
        print(
            "Soil moisture sensor initialized successfully, test reading:",
            test_moisture,
        )
        sensor_status["soil_moisture"] = True
    except Exception as e:
        print("Soil moisture initialization failed:", e)
        soil_moisture_adc = None
        sensor_status["soil_moisture"] = False
    time.sleep(1)


def connect_wifi():
    """
    Establish WiFi connection with automatic retry mechanism.

    Attempts to connect to WiFi network using global ssid and password.
    Retries up to 10 times with 2-second delays between attempts.
    Updates connection_status dictionary with WiFi status.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global wlan
    if wlan is None:
        print("Setting up WiFi...")
        wlan = network.WLAN(network.STA_IF)

    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting to WiFi...")
        wlan.connect(ssid, password)
        attempt = 0
        while not wlan.isconnected() and attempt < 10:
            time.sleep(2)
            attempt += 1
            print(f"WiFi connection attempt {attempt}/10")

    connected = wlan.isconnected()
    connection_status["wifi"] = connected

    if connected:
        print("Connected to WiFi:", wlan.ifconfig())
        return True
    else:
        print("Failed to connect to WiFi")
        return False


def connect_mqtt():
    """
    Establish MQTT connection to broker with authentication.

    Creates MQTTClient instance with global broker credentials and connects
    to the MQTT broker. Includes connection testing by publishing a test message.
    Handles cleanup of existing connections and error management.

    Returns:
        bool: True if connection successful, False otherwise
    """
    global mqtt_client
    try:
        if mqtt_client is not None:
            try:
                mqtt_client.disconnect()
            except:
                pass
        print(f"Attempting MQTT connection to {mqtt_broker}:{mqtt_port}")
        mqtt_client = MQTTClient(
            client_id,
            mqtt_broker,
            port=mqtt_port,
            user=mqtt_user,
            password=mqtt_password,
            keepalive=120,
        )

        mqtt_client.connect()
        print("Connected to MQTT broker")
        connection_status["mqtt"] = True

        # Test the connection with a simple publish
        test_topic = f"homeassistant/sensor/pico_w_01/test/state"
        mqtt_client.publish(test_topic, "connected")
        print("MQTT connection test successful")
        return True

    except Exception as e:
        print("MQTT connection failed:", e)
        mqtt_client = None
        connection_status["mqtt"] = False
        return False


def is_mqtt_connected():
    """
    Check if MQTT client is currently connected.

    Performs a lightweight check of MQTT connection status by verifying
    both client existence and connection status flag.

    Returns:
        bool: True if MQTT client exists and is connected, False otherwise
    """
    return mqtt_client is not None and connection_status["mqtt"]


def publish_discovery_config():
    """
    Publish Home Assistant discovery configurations for all sensors.

    Publishes MQTT discovery configurations for temperature, humidity, light,
    soil moisture, and device status sensors. Uses proper Home Assistant
    device classes and measurement units to enable automatic entity creation
    and statistics tracking.

    Returns:
        None
    """
    global mqtt_client
    if not is_mqtt_connected() or mqtt_client is None:
        print("MQTT not connected, skipping discovery config")
        return

    # Define sensors with proper Home Assistant device classes
    sensors = [
        {
            "id": "humidity",
            "name": "Humidity",
            "device_class": "humidity",
            "unit": "%",
            "state_class": "measurement",
            "force_update": True,
        },
        {
            "id": "temperature",
            "name": "Temperature",
            "device_class": "temperature",
            "unit": "°C",
            "state_class": "measurement",
            "force_update": True,
        },
        {
            "id": "lux",
            "name": "Light Level",
            "device_class": "illuminance",
            "unit": "lx",
            "state_class": "measurement",
            "force_update": True,
        },
        {
            "id": "soil_moisture",
            "name": "Soil Moisture",
            "device_class": "moisture",
            "unit": "%",
            "state_class": "measurement",
            "force_update": True,
        },
        {
            "id": "status",
            "name": "Device Status",
            "icon": "mdi:check-circle",
            "force_update": True,
        },
    ]

    for sensor in sensors:
        config_topic = f"homeassistant/sensor/pico_w_01/{sensor['id']}/config"
        state_topic = f"homeassistant/sensor/pico_w_01/{sensor['id']}/state"

        config = {
            "name": sensor["name"],
            "state_topic": state_topic,
            "unique_id": f"pico_w_01_{sensor['id']}",
            "device": {
                "identifiers": ["pico_w_01"],
                "name": DEVICE_NAME,
                "manufacturer": DEVICE_MANUFACTURER,
                "model": DEVICE_MODEL,
                "sw_version": DEVICE_VERSION,
            },
            "force_update": sensor.get("force_update", False),
        }

        # Add device_class for standard sensors
        if sensor.get("device_class"):
            config["device_class"] = sensor["device_class"]

        # Add unit of measurement
        if sensor.get("unit"):
            config["unit_of_measurement"] = sensor["unit"]

        # Add state_class for measurement sensors (enables statistics)
        if sensor.get("state_class"):
            config["state_class"] = sensor["state_class"]

        # Only add icon for custom sensors without device_class
        if sensor.get("icon") and not sensor.get("device_class"):
            config["icon"] = sensor["icon"]
        try:
            if mqtt_client is not None:
                mqtt_client.publish(
                    config_topic, json.dumps(config).encode("utf-8"), retain=True
                )
                print(f"Discovery config published for {sensor['id']}")
                time.sleep(0.2)  # Small delay between publishes
            else:
                print(
                    f"Cannot publish discovery for {sensor['id']}: MQTT client is None"
                )
        except Exception as e:
            print(f"Failed to publish discovery for {sensor['id']}: {e}")


def safe_publish(topic, value, retain=False):
    """
    Safely publish a value to an MQTT topic with error handling.

    Args:
        topic (str): MQTT topic to publish to
        value: Value to publish (will be converted to string)
        retain (bool): MQTT retain flag, default False

    Returns:
        bool: True if publish successful, False otherwise
    """
    if not is_mqtt_connected():
        return False
    try:
        mqtt_client.publish(topic, str(value), retain=retain)
        print(f"Published {value} to {topic} with retain={retain}")
        return True
    except Exception as e:
        print(f"Publish failed to {topic}: {e}")
        connection_status["mqtt"] = False  # Mark as disconnected on failure
        return False


def publish_sensor_data(temp, hum, lux, moisture):
    """
    Publish all sensor data to individual MQTT topics.

    Publishes temperature, humidity, light level, and soil moisture data
    to separate MQTT topics using the safe_publish function. Counts
    successful publications for monitoring purposes.

    Args:
        temp (float): Temperature reading in Celsius
        hum (float): Humidity reading in percentage
        lux (float): Light level reading in lux
        moisture (float): Soil moisture reading in percentage

    Returns:
        int: Number of successful sensor data publications
    """
    if not is_mqtt_connected():
        print("MQTT not connected, skipping publish")
        return 0

    sensors_data = [
        ("temperature", temp),
        ("humidity", hum),
        ("lux", lux),
        ("soil_moisture", moisture),
    ]

    published_count = 0
    for sensor_type, value in sensors_data:
        if value is not None:
            # Use consistent topic structure with discovery
            topic = f"homeassistant/sensor/pico_w_01/{sensor_type}/state"
            if safe_publish(topic, value, retain=True):
                published_count += 1

    return published_count


def publish_device_status():
    """
    Publish comprehensive device status information.

    Evaluates overall device health based on WiFi connectivity, MQTT connection,
    sensor functionality, and recent successful data publications. Publishes
    status strings like "online", "offline", "degraded", or "warning" to help
    monitor device health remotely.

    Returns:
        bool: True if status published successfully, False otherwise
    """
    topic = "homeassistant/sensor/pico_w_01/status/state"  # Updated to match discovery

    # Count working sensors
    working_sensors = sum(
        [
            sensor_status["dht11"] and failed_sensor_reads["dht11"] < 5,
            sensor_status["bh1750"] and failed_sensor_reads["bh1750"] < 5,
            sensor_status["soil_moisture"] and failed_sensor_reads["soil_moisture"] < 5,
        ]
    )

    total_sensors = sum(
        [
            sensor_status["dht11"],
            sensor_status["bh1750"],
            sensor_status["soil_moisture"],
        ]
    )

    # Determine overall status
    if not connection_status["wifi"]:
        status = "WiFi Disconnected"
    elif not connection_status["mqtt"]:
        status = "MQTT Disconnected"
    elif working_sensors == 0:
        status = "All Sensors Failed"
    elif working_sensors < total_sensors:
        status = f"Partial ({working_sensors}/{total_sensors} sensors)"
    elif time.time() - connection_status["last_successful_publish"] > 300:
        status = "Publish Timeout"
    else:
        status = "Online"

    return safe_publish(topic, status)


def update_oled(temp, hum, lux, moisture):
    """
    Update the OLED display with current sensor readings.

    Displays formatted sensor data on the SSD1306 OLED screen, showing
    light level, temperature, humidity, and soil moisture. Handles cases
    where sensor values are None by displaying "--" placeholders.

    Args:
        temp (float): Temperature reading in Celsius
        hum (float): Humidity reading in percentage
        lux (float): Light level reading in lux
        moisture (float): Soil moisture reading in percentage

    Returns:
        None
    """
    if oled is None:
        return
    try:
        oled.fill(0)
        oled.text("Lux: {:.1f}".format(lux) if lux is not None else "Lux: --", 0, 0)
        oled.text(
            "Temp: {:.1f}C".format(temp) if temp is not None else "Temp: --", 0, 16
        )
        oled.text(
            "Humidity: {:.1f}%".format(hum) if hum is not None else "Humidity: --",
            0,
            32,
        )
        oled.text(
            (
                "Moisture: {:.1f}%".format(moisture)
                if moisture is not None
                else "Moisture: --"
            ),
            0,
            48,
        )
        oled.show()
    except Exception as e:
        print("OLED update failed:", e)


def get_soil_moisture_percent(raw_value, dry=SOIL_MOISTURE_DRY, wet=SOIL_MOISTURE_WET):
    """
    Convert raw ADC soil moisture reading to percentage.

    Converts raw 16-bit ADC values from capacitive soil moisture sensor
    to percentage values using calibrated dry and wet reference points.
    Higher ADC values indicate drier soil, lower values indicate wetter soil.

    Args:
        raw_value (int): Raw ADC reading from soil moisture sensor
        dry (int): ADC value for completely dry soil (default: 41000)
        wet (int): ADC value for completely wet soil (default: 18000)

    Returns:
        int: Soil moisture percentage (0-100)
    """
    raw_value = max(min(raw_value, dry), wet)
    percent = int((dry - raw_value) * 100 / (dry - wet))
    return percent


def safe_sensor_read(sensor_name, read_function):
    """
    Generic function for safe sensor reading with failure tracking.

    Executes a sensor read function with exception handling and tracks
    consecutive failures. Resets failure count on successful reads.
    Helps identify problematic sensors for maintenance purposes.

    Args:
        sensor_name (str): Name of the sensor for failure tracking
        read_function (callable): Function to execute for sensor reading

    Returns:
        Any: Result of read_function if successful, None if failed
    """
    try:
        result = read_function()
        failed_sensor_reads[sensor_name] = 0
        return result
    except Exception as e:
        failed_sensor_reads[sensor_name] += 1
        if failed_sensor_reads[sensor_name] >= 5:
            print(
                f"{sensor_name} sensor failed {failed_sensor_reads[sensor_name]} times: {e}"
            )
        return None


def read_sensors_once():
    """
    Read all sensors once and return their values.

    Performs a single reading from all connected sensors (DHT11, BH1750,
    soil moisture) using safe_sensor_read for error handling. Converts
    raw soil moisture ADC values to percentage using calibrated reference points.

    Returns:
        tuple: (temperature, humidity, lux, moisture_percent) - any value
               can be None if sensor reading failed
    """

    # DHT11 reading
    def read_dht():
        if dht_sensor is None:
            return None, None
        dht_sensor.measure()
        return dht_sensor.temperature(), dht_sensor.humidity()

    temp, hum = safe_sensor_read("dht11", read_dht) or (None, None)

    # Light sensor reading
    lux = safe_sensor_read(
        "bh1750",
        lambda: light_sensor.luminance(BH1750.ONCE_HIRES_1) if light_sensor else None,
    )

    # Soil moisture reading
    moisture_raw = safe_sensor_read(
        "soil_moisture",
        lambda: soil_moisture_adc.read_u16() if soil_moisture_adc else None,
    )
    moisture = (
        get_soil_moisture_percent(moisture_raw) if moisture_raw is not None else None
    )

    return temp, hum, lux, moisture


# Initialize everything
print("Initializing sensors...")
initialize_sensors()

print("All sensors initialized, starting connection setup...")

# Connect to WiFi and MQTT
if not connect_wifi():
    print("Initial WiFi connection failed, continuing and will retry in loop")

if not connect_mqtt():
    print("Initial MQTT connection failed, will retry in loop")
else:
    time.sleep(1)
    publish_discovery_config()
    publish_device_status()


# Add this function after your other functions
def force_gc():
    """
    Force garbage collection and print memory statistics.

    Manually triggers garbage collection to free up memory and prints
    current memory usage statistics. Issues a warning if available
    memory drops below 10KB threshold.

    Returns:
        None
    """
    gc.collect()
    free_mem = gc.mem_free()
    alloc_mem = gc.mem_alloc()
    print(f"Memory - Free: {free_mem}, Allocated: {alloc_mem}")
    if free_mem < 10000:  # Less than 10KB free
        print("WARNING: Low memory!")


# Main loop with averaging
last_publish_time = 0
last_sensor_read_time = 0
last_connection_check = 0
last_status_update = 0
last_gc_time = 0  # Add this for better GC timing

# Lists to store readings for averaging
temp_readings = []
hum_readings = []
lux_readings = []
moisture_readings = []

print("Starting sensor loop...")

while True:
    current_time = time.time()

    # MQTT keepalive - call this frequently to maintain connection
    if is_mqtt_connected() and mqtt_client is not None:
        try:
            mqtt_client.check_msg()  # This maintains the keepalive
        except Exception as e:
            print(f"MQTT check_msg failed: {e}")
            connection_status["mqtt"] = False

    # Force garbage collection every 5 minutes
    if current_time - last_gc_time >= 300:  # Every 5 minutes
        force_gc()
        last_gc_time = current_time

    # Check connections every 60 seconds
    if current_time - last_connection_check >= 60:
        wifi_was_connected = connection_status["wifi"]
        mqtt_was_connected = connection_status["mqtt"]

        if wlan is None or not wlan.isconnected():
            print("WiFi disconnected, attempting to reconnect...")
            connect_wifi()
        else:
            connection_status["wifi"] = True

        if mqtt_client is not None:
            try:
                mqtt_client.ping()
                connection_status["mqtt"] = True
            except:
                print("MQTT ping failed, attempting to reconnect...")
                connection_status["mqtt"] = False
                connect_mqtt()
                if is_mqtt_connected():
                    publish_discovery_config()
                    publish_device_status()
        else:
            connection_status["mqtt"] = False

        # Publish status update if connection state changed
        if (
            wifi_was_connected != connection_status["wifi"]
            or mqtt_was_connected != connection_status["mqtt"]
        ):
            publish_device_status()

        last_connection_check = current_time

    # Publish status update periodically
    if current_time - last_status_update >= STATUS_UPDATE_INTERVAL:
        publish_device_status()
        last_status_update = current_time

    # Read sensors every SENSOR_READ_INTERVAL seconds
    if current_time - last_sensor_read_time >= SENSOR_READ_INTERVAL:
        temp, hum, lux, moisture = read_sensors_once()

        # Store valid readings
        if temp is not None:
            temp_readings.append(temp)
        if hum is not None:
            hum_readings.append(hum)
        if lux is not None:
            lux_readings.append(lux)
        if moisture is not None:
            moisture_readings.append(moisture)

        last_sensor_read_time = current_time

    # Publish averaged values every PUBLISH_INTERVAL seconds
    if current_time - last_publish_time >= PUBLISH_INTERVAL:
        # Calculate averages
        avg_temp = sum(temp_readings) / len(temp_readings) if temp_readings else None
        avg_hum = sum(hum_readings) / len(hum_readings) if hum_readings else None
        avg_lux = sum(lux_readings) / len(lux_readings) if lux_readings else None
        avg_moisture = (
            sum(moisture_readings) / len(moisture_readings)
            if moisture_readings
            else None
        )

        update_oled(avg_temp, avg_hum, avg_lux, avg_moisture)
        print(
            f"Calculated averages -> Temp: {avg_temp}, Hum: {avg_hum}, Lux: {avg_lux}, Moisture: {avg_moisture}"
        )

        # Publish data
        published_count = publish_sensor_data(avg_temp, avg_hum, avg_lux, avg_moisture)

        if published_count > 0:
            connection_status["last_successful_publish"] = current_time
            print(f"Successfully published {published_count}/4 sensor values")
        else:
            print("MQTT not connected, skipping publish")

        # Clear readings for next averaging period
        for readings_list in [
            temp_readings,
            hum_readings,
            lux_readings,
            moisture_readings,
        ]:
            readings_list.clear()

        last_publish_time = current_time

    time.sleep(0.5)

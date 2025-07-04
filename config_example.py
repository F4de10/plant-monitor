# Configuration file for Plant Monitor
# COPY THIS FILE TO config.py AND UPDATE WITH YOUR ACTUAL VALUES

# WiFi Configuration
WIFI_SSID = "your_wifi_name"
WIFI_PASSWORD = "your_wifi_password"

# MQTT Broker Configuration
MQTT_BROKER = "192.168.1.100"  # IP address of your MQTT broker
MQTT_PORT = 1883 
MQTT_USERNAME = "your_mqtt_username"
MQTT_PASSWORD = "your_mqtt_password"
MQTT_CLIENT_ID = "pico_w_sensor_01"

# Sensor Configuration
SENSOR_READ_INTERVAL = 6    # seconds between individual sensor reads
PUBLISH_INTERVAL = 60       # seconds between publishing averaged data
STATUS_UPDATE_INTERVAL = 300  # seconds between status updates

# Soil Moisture Calibration (adjust these values for your sensor)
SOIL_MOISTURE_DRY = 41000   # ADC value for completely dry soil
SOIL_MOISTURE_WET = 18000   # ADC value for completely wet soil

# GPIO Pin Configuration
PIN_DHT11 = 22              # DHT11 data pin
PIN_I2C_SCL = 5            # I2C clock pin for BH1750 and OLED
PIN_I2C_SDA = 4            # I2C data pin for BH1750 and OLED
PIN_SOIL_MOISTURE = 26     # ADC pin for soil moisture sensor

# Device Information
DEVICE_NAME = "Pico W Plant Sensor"
DEVICE_VERSION = "1.0"
DEVICE_MANUFACTURER = "Raspberry Pi"
DEVICE_MODEL = "Raspberry Pi Pico W"

import sys
import time
import struct
import serial
import signal

################################################################################
################################################################################

# A simple sigint handler to stop the reading
def sigint_handler(signal, frame):
	dataFile.close()
	sp.close()
	sys.exit(0)

################################################################################
################################################################################

# Check for minimum arguments
if (len(sys.argv) < 3):
	print "Usage: %s <serial port> <output file>" % sys.argv[0]
	sys.exit(1)

# Open our data file
try:
	dataFile = open(sys.argv[2], "w")
except IOError as (strError):
	print "Error opening file: %s" % strError

# Open the serial port
try:
	sp = serial.Serial(sys.argv[1], baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1);
except serial.SerialException as (strError):
	print "Error opening serial port!: ", strError
	sys.exit(1)

# Set up our signal handler
signal.signal(signal.SIGINT, sigint_handler)

while True:
	# Read raw data from the serial port
	rawData = sp.read(128)
	# Write to the data file
	if (len(rawData) > 0):
		dataFile.write(rawData)
		dataFile.flush()


